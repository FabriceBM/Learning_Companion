"""Photos of a lesson, or a notion parents flagged, -> a structured lesson (Claude API).

Runs on the server: the API key never ships in the app. The result goes to the
family's review inbox, not straight into the schedule.
"""

from __future__ import annotations

import base64
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from anthropic import Anthropic

from lc_engine import KnowledgeUnit

from .schema import Lesson

MODEL = "claude-opus-5-5"

# Stable across calls so it can be cached; the per-lesson details go in the user turn.
SYSTEM = """You turn photos of a school lesson (notebook pages, worksheets, textbook pages) into material for spaced retrieval practice for a child.

Split the lesson into small units of knowledge: one word, one rule, one date, one method, one idea per unit. Treat every subject as a language: vocabulary, spelling and grammar rules, dates, formulas and methods are all units.

Keep the teacher's wording in "statement" wherever the photo has it: the child is assessed on the teacher's version. Write questions in the language of the lesson, at the child's level, and never make a question that can be answered without knowing the unit. For maths methods, write questions with fresh numbers rather than the worked example from the page.

Name each unit's "notion" generically, the way it would appear on a map of knowledge independent of any school system or grade.

When the page is meant to be learned by heart (a poem, a definition or rule marked to learn, a text to recite), set "mode" to "by_heart" and copy the text exactly into "verbatim_text", keeping line breaks and punctuation; the app cuts it into chunks itself. When a map or diagram has labels to know, list each label with an approximate box so it can be blanked; a person adjusts the boxes in the review inbox.

Copy the text each unit comes from into "source_quote". When handwriting or the photo is unclear, say so with "uncertain" and in "unreadable_parts" rather than guessing."""

TEACH = """You write a short lesson for one notion that a parent found missing in their child's knowledge, as material for spaced retrieval practice. There is no photo: the lesson is yours.

Assume the listed prerequisites are known and build on them; do not re-teach them. Split the notion into small units (one idea or step each), clear enough for the child's age, with a statement, questions at several levels, and the usual misconceptions. This is for practice in free sessions, not word-for-word learning: for every rule or method, write at least eight varied apply-level questions (different verbs and persons for a conjugation, different numbers for a method) so practice never repeats the same item. Name every unit's "notion" with the notion given. Set "mode" to "understand", "verbatim_text" to null and "figure_labels" to empty. Leave "source_quote" empty and "uncertain" false; "unreadable_parts" is empty."""

MediaType = Literal["image/jpeg", "image/png", "image/webp"]


@dataclass(frozen=True)
class Photo:
    data: bytes
    media_type: MediaType


@dataclass(frozen=True)
class LessonContext:
    level: str
    """e.g. "6e (France, cycle 3)", "CE2", "adult, Spanish B1"."""
    subject_hint: str | None = None
    """If the family already said which subject this is."""


class LessonRequestError(RuntimeError):
    """The model declined, ran out of room, or returned something that is not a lesson."""


def extract_lesson(client: Anthropic, photos: Sequence[Photo], context: LessonContext) -> Lesson:
    """Photo(s) of one lesson -> structured lesson."""
    content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": p.media_type, "data": base64.standard_b64encode(p.data).decode("ascii")},
        }
        for p in photos
    ]
    subject = f" Subject: {context.subject_hint}." if context.subject_hint else ""
    content.append({"type": "text", "text": f"Level: {context.level}.{subject} Extract the lesson."})
    return _request_lesson(client, SYSTEM, content)


@dataclass(frozen=True)
class NotionRequest:
    notion: str
    """As the parent wrote it, or as named on the knowledge map."""
    learner_age: int
    language: str
    """Language the child learns in, e.g. "fr"."""
    known_prerequisites: Sequence[str] = field(default_factory=tuple)
    """Notions already known (from the placement check), to build on rather than re-teach."""
    why: str | None = None
    """Optional context from the parent: "starts high school next September"."""


def teach_notion(client: Anthropic, request: NotionRequest) -> Lesson:
    """A gap a parent flagged, with no lesson to photograph: write the lesson.
    Same output as extract_lesson, so it goes through the same review inbox."""
    lines = [
        f"Notion: {request.notion}",
        f"Child's age: {request.learner_age}",
        f"Language: {request.language}",
        f"Already known: {'; '.join(request.known_prerequisites) or 'nothing listed'}",
    ]
    if request.why:
        lines.append(f"Why the parents flagged it: {request.why}")
    return _request_lesson(client, TEACH, [{"type": "text", "text": "\n".join(lines)}])


def _request_lesson(client: Anthropic, system: str, content: list[dict[str, Any]]) -> Lesson:
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_format=Lesson,
        output_config={"effort": "high"},
        # If the model declines (unlikely for school material), the API retries on a fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        explanation = response.stop_details.explanation if response.stop_details else None
        raise LessonRequestError(f"Lesson request declined: {explanation or 'no explanation'}")
    if response.stop_reason == "max_tokens":
        raise LessonRequestError(
            "Lesson too long for one pass: split it into smaller parts (fewer photos, or a narrower notion)."
        )
    if response.parsed_output is None:
        raise LessonRequestError("The model returned output that does not match the lesson schema.")
    return response.parsed_output


IMPORTANCE = {"nice_to_know": 1, "expected": 2, "foundational": 3}


def notion_slug(name: str) -> str:
    """A notion name -> its id on the knowledge map. The app resolves names against the existing map first."""
    plain = "".join(c for c in unicodedata.normalize("NFD", name) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def to_knowledge_units(
    lesson: Lesson,
    lesson_id: str,
    *,
    cumulative: bool,
    goal_ids: Sequence[str] = (),
    notion_id: Callable[[str], str] = notion_slug,
) -> list[KnowledgeUnit]:
    """Map an accepted lesson onto the engine's units. Cumulative subjects keep their retention target after tests."""

    def uid(key: str) -> str:
        return f"{lesson_id}/{key}"

    return [
        KnowledgeUnit(
            id=uid(u.key),
            subject=lesson.subject,
            kind=u.kind,
            title=u.title,
            notion_id=notion_id(u.notion),
            importance=IMPORTANCE[u.importance],  # type: ignore[arg-type]
            prerequisites=[uid(p) for p in u.prerequisites],
            goal_ids=goal_ids,
            cumulative=cumulative,
        )
        for u in lesson.units
    ]
