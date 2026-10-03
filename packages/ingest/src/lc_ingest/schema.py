"""What one lesson (one or more photos of a notebook or textbook page) becomes.

Everything here is reviewed by a person before it reaches the schedule.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Probe(BaseModel):
    level: Literal["recognize", "recall", "apply", "explain"] = Field(
        description="recognize = pick among choices; recall = produce it; apply = use it on new material; explain = say why"
    )
    prompt: str = Field(description="The question, in the language of the lesson, worded for the child")
    answer: str = Field(description="Expected answer; for explain, the key points a good answer contains")
    choices: list[str] | None = Field(description="Only for recognize: 3 or 4 options including the answer")
    grading: Literal["exact", "accent_sensitive", "numeric", "rubric"] = Field(
        description="accent_sensitive when spelling is the point (dictation, accents, agreement)"
    )


class Unit(BaseModel):
    key: str = Field(description='Short slug, unique within the lesson, e.g. "add-same-denominator"')
    kind: Literal["term", "fact", "rule", "procedure", "concept", "formula"]
    notion: str = Field(
        description="The general notion this unit belongs to, named without reference to any school grade, "
        'e.g. "Adding fractions with different denominators"'
    )
    title: str
    statement: str = Field(description="The knowledge itself, keeping the teacher's wording where the photo has it")
    importance: Literal["nice_to_know", "expected", "foundational"]
    prerequisites: list[str] = Field(description="Keys of other units in this lesson that must be known first")
    probes: list[Probe] = Field(description="At least one recall-level probe; add other levels when they make sense")
    misconceptions: list[str] = Field(description="Common wrong ideas about this unit, used to write wrong choices and checks")
    source_quote: str = Field(
        description="The text in the photo this unit comes from, copied as written; empty for a generated lesson"
    )
    uncertain: bool = Field(description="True when the photo was hard to read here and a person must check it")


class FigureLabel(BaseModel):
    label: str = Field(description="The label as written on the map or diagram")
    x: float = Field(description="Left edge of the label, as a fraction of the image width (0–1)")
    y: float = Field(description="Top edge, as a fraction of the image height (0–1)")
    w: float = Field(description="Width, as a fraction of the image width")
    h: float = Field(description="Height, as a fraction of the image height")


class Lesson(BaseModel):
    mode: Literal["understand", "by_heart"] = Field(
        description="by_heart when the page is to be learned word for word (a poem, a definition marked to learn, "
        "a map to know); otherwise understand"
    )
    subject: str
    language: str = Field(description='BCP 47 code of the lesson language, e.g. "fr", "es", "en"')
    title: str
    summary: str = Field(description="Two or three sentences a parent can read to know what the lesson is about")
    units: list[Unit]
    verbatim_text: str | None = Field(
        description="For a text to learn by heart: the exact text, keeping its line breaks and punctuation; null otherwise"
    )
    figure_labels: list[FigureLabel] = Field(
        description="Labels on a map or diagram to be known, with approximate boxes so they can be blanked; empty if none"
    )
    unreadable_parts: list[str] = Field(description="Where the photo could not be read, so the family can retake it")
