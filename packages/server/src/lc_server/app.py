"""The family server.

It does the two things a phone should not: hold the Claude API key (lesson
photos -> lessons, flagged notions -> lessons) and refit each learner's memory
model on their review log (weekly). Everything else runs on the phone, offline.

    ANTHROPIC_API_KEY=... LC_FAMILY_TOKEN=... uv run lc-server

Lessons come back to the family's review inbox; nothing reaches a schedule
until a parent accepts it. The server stores nothing: the phone keeps the
review log, which is the source of truth.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime
from typing import Annotated, Any, Literal

from anthropic import Anthropic
from fastapi import Depends, FastAPI, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from lc_engine import DEFAULT_TUNING, Rating, ReviewRecord, fit_weights
from lc_ingest import Lesson, LessonContext, LessonRequestError, NotionRequest, Photo, extract_lesson, teach_notion

MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTOS = 6
MAX_PHOTO_BYTES = 8 * 1024 * 1024


class NotionIn(BaseModel):
    notion: str = Field(description='As the parent wrote it, e.g. "French › Conjugation › Passé simple"')
    learner_age: int = Field(ge=5, le=99)
    language: str = Field(description='Language the child learns in, e.g. "fr"')
    known_prerequisites: list[str] = []
    why: str | None = None


class ReviewIn(BaseModel):
    ku_id: str
    at: datetime = Field(description="With its time zone, e.g. 2026-10-02T17:05:00+02:00")
    grade: Literal[1, 2, 3, 4] = Field(description="1 Again, 2 Hard, 3 Good, 4 Easy")


class FitIn(BaseModel):
    reviews: list[ReviewIn]
    same_day_reviews: bool = Field(False, description="True when the learner has several sessions a day")


class FitOut(BaseModel):
    weights: list[float] | None = Field(description="21 FSRS-6 weights, or null while the log is too short")
    reviews: int
    needed: int


def create_app(client: Any = None, family_token: str | None = None) -> FastAPI:
    """``client``: an Anthropic client (a fake one in tests). ``family_token``: the
    shared secret every family device sends; defaults to $LC_FAMILY_TOKEN."""
    app = FastAPI(title="Learning companion server", version="0.2.0")
    token = family_token if family_token is not None else os.environ.get("LC_FAMILY_TOKEN")
    state: dict[str, Any] = {"client": client}

    def anthropic_client() -> Any:
        if state["client"] is None:
            state["client"] = Anthropic()
        return state["client"]

    def family(authorization: Annotated[str | None, Header()] = None) -> None:
        if token and not (authorization and secrets.compare_digest(authorization, f"Bearer {token}")):
            raise HTTPException(status_code=401, detail="This server answers only the family's devices.")

    guarded = [Depends(family)]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/lessons", dependencies=guarded)
    async def read_lesson(
        photos: list[UploadFile],
        level: Annotated[str, Form(description='e.g. "6e (France, cycle 3)"')],
        subject_hint: Annotated[str | None, Form()] = None,
    ) -> Lesson:
        """Photos of one lesson -> a lesson for the review inbox."""
        if not 1 <= len(photos) <= MAX_PHOTOS:
            raise HTTPException(status_code=422, detail=f"Send 1 to {MAX_PHOTOS} photos of the same lesson.")
        images = []
        for upload in photos:
            if upload.content_type not in MEDIA_TYPES:
                raise HTTPException(status_code=415, detail=f"{upload.filename}: send a JPEG, PNG or WebP photo.")
            data = await upload.read()
            if len(data) > MAX_PHOTO_BYTES:
                raise HTTPException(status_code=413, detail=f"{upload.filename}: photo larger than 8 MB.")
            images.append(Photo(data, upload.content_type))  # type: ignore[arg-type]
        try:
            return extract_lesson(anthropic_client(), images, LessonContext(level, subject_hint))
        except LessonRequestError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/notions", dependencies=guarded)
    def write_lesson(request: NotionIn) -> Lesson:
        """A notion parents flagged -> a generated lesson for the review inbox."""
        try:
            return teach_notion(anthropic_client(), NotionRequest(**request.model_dump()))
        except LessonRequestError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/learners/{learner_id}/fit", dependencies=guarded)
    def fit(learner_id: str, body: FitIn) -> FitOut:
        """One learner's review log -> memory-model weights fitted to them."""
        log = [ReviewRecord(r.ku_id, r.at, Rating(r.grade)) for r in body.reviews]
        weights = fit_weights(log, same_day_reviews=body.same_day_reviews)
        return FitOut(weights=weights, reviews=len(log), needed=DEFAULT_TUNING.memory.min_reviews_to_fit)

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host=os.environ.get("LC_HOST", "127.0.0.1"), port=int(os.environ.get("LC_PORT", "8787")))
