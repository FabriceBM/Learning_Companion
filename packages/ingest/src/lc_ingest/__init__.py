"""Lesson photo, or a notion parents flagged, -> knowledge units and questions (Claude API)."""

from .extract import (
    MODEL,
    LessonContext,
    LessonRequestError,
    NotionRequest,
    Photo,
    extract_lesson,
    notion_slug,
    teach_notion,
    to_knowledge_units,
)
from .schema import FigureLabel, Lesson, Probe, Unit

__all__ = [
    "MODEL",
    "FigureLabel",
    "Lesson",
    "LessonContext",
    "LessonRequestError",
    "NotionRequest",
    "Photo",
    "Probe",
    "Unit",
    "extract_lesson",
    "notion_slug",
    "teach_notion",
    "to_knowledge_units",
]
