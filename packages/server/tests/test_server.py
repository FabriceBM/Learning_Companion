import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from lc_ingest import Lesson
from lc_server import create_app

CORBEAU = Lesson.model_validate(
    json.loads((Path(__file__).resolve().parents[2] / "ingest" / "fixtures" / "corbeau.json").read_text(encoding="utf-8"))
)
AUTH = {"Authorization": "Bearer family-secret"}


class FakeClient:
    def __init__(self, **response):
        self.calls = []
        defaults = {"stop_reason": "end_turn", "stop_details": None, "parsed_output": CORBEAU}
        self._response = SimpleNamespace(**{**defaults, **response})
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def server(**response) -> tuple[TestClient, FakeClient]:
    fake = FakeClient(**response)
    return TestClient(create_app(client=fake, family_token="family-secret")), fake


def test_answers_only_the_family():
    http, _ = server()
    assert http.get("/health").status_code == 200
    assert http.post("/notions", json={"notion": "x", "learner_age": 12, "language": "fr"}).status_code == 401
    wrong = {"Authorization": "Bearer guess"}
    assert http.post("/notions", json={"notion": "x", "learner_age": 12, "language": "fr"}, headers=wrong).status_code == 401


def test_reads_a_photographed_lesson_into_the_review_inbox():
    http, fake = server()
    files = [("photos", ("page1.jpg", b"\xff\xd8jpeg", "image/jpeg")), ("photos", ("page2.png", b"png", "image/png"))]
    response = http.post("/lessons", files=files, data={"level": "6e", "subject_hint": "French"}, headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "by_heart"
    content = fake.calls[0]["messages"][0]["content"]
    assert [c["type"] for c in content] == ["image", "image", "text"]


def test_rejects_what_is_not_a_photo():
    http, fake = server()
    files = [("photos", ("notes.pdf", b"%PDF", "application/pdf"))]
    assert http.post("/lessons", files=files, data={"level": "6e"}, headers=AUTH).status_code == 415
    assert fake.calls == []


def test_writes_a_lesson_for_a_pushed_notion_and_reports_a_decline():
    http, _ = server()
    body = {"notion": "Passé simple", "learner_age": 13, "language": "fr", "known_prerequisites": ["Present"]}
    assert http.post("/notions", json=body, headers=AUTH).status_code == 200
    declined, _ = server(stop_reason="refusal", stop_details=SimpleNamespace(explanation="policy"))
    response = declined.post("/notions", json=body, headers=AUTH)
    assert response.status_code == 422
    assert "declined" in response.json()["detail"]


def test_fits_a_learner_once_the_log_is_long_enough():
    http, _ = server()
    start = datetime(2026, 9, 1, 17, tzinfo=ZoneInfo("Europe/Paris"))
    short = {"reviews": [{"ku_id": "a", "at": start.isoformat(), "grade": 3}]}
    assert http.post("/learners/lea/fit", json=short, headers=AUTH).json() == {"weights": None, "reviews": 1, "needed": 400}

    reviews = []
    for u in range(110):
        day = 0
        for k, gap in enumerate((0, 1, 3, 7)):
            day += gap
            grade = 1 if (u + k) % 7 == 0 else 3
            reviews.append({"ku_id": f"u{u}", "at": (start + timedelta(days=day)).isoformat(), "grade": grade})
    fitted = http.post("/learners/lea/fit", json={"reviews": reviews}, headers=AUTH).json()
    assert len(fitted["weights"]) == 21
    assert fitted["reviews"] == 440
