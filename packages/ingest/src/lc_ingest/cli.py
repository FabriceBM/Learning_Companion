"""Try the extraction on your own photos:

    uv run lc-extract "6e" lesson-p1.jpg lesson-p2.jpg

Credentials come from the environment (ANTHROPIC_API_KEY or an `ant auth login` profile).
"""

from __future__ import annotations

import sys
from pathlib import Path

from anthropic import Anthropic

from .extract import LessonContext, MediaType, Photo, extract_lesson

TYPES: dict[str, MediaType] = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print("Usage: lc-extract <level> <photo> [photo...]", file=sys.stderr)
        return 1
    level, *paths = args
    photos = []
    for p in map(Path, paths):
        media_type = TYPES.get(p.suffix.lower())
        if media_type is None:
            print(f"{p}: use a .jpg, .png or .webp photo", file=sys.stderr)
            return 1
        photos.append(Photo(p.read_bytes(), media_type))
    lesson = extract_lesson(Anthropic(), photos, LessonContext(level))
    print(lesson.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
