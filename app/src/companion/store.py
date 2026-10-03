"""Offline storage on the phone: one SQLite file.

The review log is append-only and is the source of truth; memory states are
rebuilt from it (and the server refits the memory model from the same log).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY,
    learner_id TEXT NOT NULL,
    ku_id TEXT NOT NULL,
    at TEXT NOT NULL,          -- ISO 8601 with offset
    grade INTEGER NOT NULL,    -- 1 Again, 2 Hard, 3 Good, 4 Easy
    latency_ms INTEGER NOT NULL,
    question_id TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    learner_id TEXT NOT NULL,
    mission_id TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    answers INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting'  -- waiting -> read -> accepted
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def data_dir() -> Path:
    """Flet sets FLET_APP_STORAGE_DATA to the app's private, persistent folder on the phone."""
    folder = Path(os.environ.get("FLET_APP_STORAGE_DATA") or Path.home() / ".learning-companion")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@dataclass(frozen=True)
class Review:
    ku_id: str
    at: datetime
    grade: int
    latency_ms: int
    question_id: str | None


class Store:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else data_dir() / "companion.db"
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.executescript(SCHEMA)

    # ------------------------------------------------------------ review log

    def add_review(self, learner_id: str, ku_id: str, at: datetime, grade: int, latency_ms: int, question_id: str | None) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO review_log (learner_id, ku_id, at, grade, latency_ms, question_id) VALUES (?, ?, ?, ?, ?, ?)",
                (learner_id, ku_id, at.isoformat(), grade, latency_ms, question_id),
            )

    def reviews(self, learner_id: str) -> Iterator[Review]:
        rows = self.db.execute(
            "SELECT ku_id, at, grade, latency_ms, question_id FROM review_log WHERE learner_id = ? ORDER BY at, id", (learner_id,)
        )
        for ku_id, at, grade, latency_ms, question_id in rows:
            yield Review(ku_id, datetime.fromisoformat(at), grade, latency_ms, question_id)

    def review_count(self, learner_id: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM review_log WHERE learner_id = ?", (learner_id,)).fetchone()[0]

    # ------------------------------------------------------------ sessions

    def start_session(self, learner_id: str, mission_id: str | None, at: datetime) -> int:
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO sessions (learner_id, mission_id, started_at) VALUES (?, ?, ?)",
                (learner_id, mission_id, at.isoformat()),
            )
        return int(cursor.lastrowid or 0)

    def end_session(self, session_id: int, at: datetime, answers: int) -> None:
        with self.db:
            self.db.execute("UPDATE sessions SET ended_at = ?, answers = ? WHERE id = ?", (at.isoformat(), answers, session_id))

    def sessions_on(self, learner_id: str, day: datetime) -> list[tuple[datetime, datetime | None, int]]:
        """Sessions that started on ``day`` (local date) and had at least one answer."""
        rows = self.db.execute(
            "SELECT started_at, ended_at, answers FROM sessions WHERE learner_id = ? AND answers > 0 ORDER BY started_at",
            (learner_id,),
        )
        out = []
        for started, ended, answers in rows:
            start = datetime.fromisoformat(started).astimezone(day.tzinfo)
            if start.date() == day.date():
                out.append((start, datetime.fromisoformat(ended).astimezone(day.tzinfo) if ended else None, answers))
        return out

    # ------------------------------------------------------------ photos

    def add_photo(self, path: str, at: datetime) -> None:
        with self.db:
            self.db.execute("INSERT INTO photos (path, taken_at) VALUES (?, ?)", (path, at.isoformat()))

    def photos(self) -> list[tuple[str, str, str]]:
        return list(self.db.execute("SELECT path, taken_at, status FROM photos ORDER BY id DESC"))

    # ------------------------------------------------------------ settings

    def get(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
