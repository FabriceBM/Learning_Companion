import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lc_engine import by_heart_units, chunk_text
from lc_ingest import (
    MODEL,
    Lesson,
    LessonContext,
    LessonRequestError,
    NotionRequest,
    Photo,
    extract_lesson,
    notion_slug,
    teach_notion,
    to_knowledge_units,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def fixture(name: str) -> Lesson:
    return Lesson.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_accepts_the_example_lesson():
    lesson = fixture("fractions.json")
    assert lesson.mode == "understand"
    assert len(lesson.units) > 3


def test_maps_a_lesson_onto_engine_units_with_namespaced_prerequisites():
    units = to_knowledge_units(fixture("fractions.json"), "maths-l7", goal_ids=["maths-test-1"], cumulative=True)
    add = next(u for u in units if u.id == "maths-l7/addition-denominateur-multiple")
    assert add.prerequisites == ("maths-l7/fractions-egales", "maths-l7/addition-meme-denominateur")
    assert add.importance == 2
    assert add.goal_ids == ("maths-test-1",)
    assert add.notion_id == "adding-and-subtracting-fractions"


def test_a_lesson_to_learn_by_heart_keeps_its_exact_text_which_the_engine_chunks():
    corbeau = fixture("corbeau.json")
    assert corbeau.mode == "by_heart"
    chunks = chunk_text(corbeau.verbatim_text, 12)
    units = by_heart_units("corbeau", corbeau.title, corbeau.subject, chunks)
    assert len(chunks) == 4
    assert "whole text" in units[-1].title


def test_notion_slug():
    assert notion_slug("Passé simple (indicatif)") == "passe-simple-indicatif"
    assert notion_slug("  Adding fractions!  ") == "adding-fractions"


class FakeClient:
    """Records the request and returns a canned response, so no API call is made."""

    def __init__(self, **response):
        self.calls = []
        defaults = {"stop_reason": "end_turn", "stop_details": None, "parsed_output": fixture("corbeau.json")}
        self._response = SimpleNamespace(**{**defaults, **response})
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def test_extract_sends_the_photos_with_a_schema_and_fallbacks():
    client = FakeClient()
    lesson = extract_lesson(client, [Photo(b"\xff\xd8jpeg", "image/jpeg")], LessonContext("6e", subject_hint="French"))
    assert lesson.mode == "by_heart"
    call = client.calls[0]
    assert call["model"] == MODEL
    assert call["output_format"] is Lesson
    assert call["output_config"] == {"effort": "high"}
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    content = call["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/jpeg"
    assert content[-1]["text"] == "Level: 6e. Subject: French. Extract the lesson."


def test_teach_builds_on_what_is_known():
    client = FakeClient(parsed_output=fixture("fractions.json"))
    teach_notion(client, NotionRequest("Passé simple", 13, "fr", ["Verb groups", "Present"], why="high school next year"))
    text = client.calls[0]["messages"][0]["content"][0]["text"]
    assert "Already known: Verb groups; Present" in text
    assert "Why the parents flagged it: high school next year" in text


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ({"stop_reason": "refusal", "stop_details": SimpleNamespace(explanation="policy")}, "declined: policy"),
        ({"stop_reason": "max_tokens"}, "too long"),
        ({"parsed_output": None}, "does not match"),
    ],
)
def test_reports_what_went_wrong(response, message):
    with pytest.raises(LessonRequestError, match=message):
        extract_lesson(FakeClient(**response), [Photo(b"x", "image/png")], LessonContext("CE2"))
