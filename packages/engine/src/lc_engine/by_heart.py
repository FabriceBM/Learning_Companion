"""Use case 1: a lesson to learn by heart (a poem, a definition, a summary, a map).

The text is cut into chunks sized for this learner, each chunk is learned with
cues that fade as memory grows, chunks are chained into longer recitations, and
everything comes back on the spaced schedule. Maps and diagrams work the same
way with their labels blanked.

Audio mode (planned, phase 2): a "listen" step reads each chunk aloud before
"read", and recitation is spoken; compare_recitation() grades the transcript.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from fsrs import Card

from .model import Attempt, KnowledgeUnit
from .tuning import DEFAULT_TUNING, ByHeartTuning

CueLevel = Literal["read", "first-letters", "key-words-blank", "recite"]
"""How much of the text is shown, from all of it to none of it."""

CUE_LEVELS: tuple[CueLevel, ...] = ("read", "first-letters", "key-words-blank", "recite")

# Letters and digits in any script: \w without the underscore.
_ALNUM = r"[^\W_]"
_WORD = re.compile(rf"{_ALNUM}+(?:[’'\-]{_ALNUM}+)*")
_WORD_WITH_JOINERS = re.compile(rf"(?:{_ALNUM}|[’'\-])+")
_SENTENCE_BREAK = re.compile(r"(?<=[,;:.!?»])\s+")


@dataclass
class Chunk:
    index: int
    text: str
    words: int


def _word_count(s: str) -> int:
    return len(s.split())


def chunk_text(text: str, chunk_words: int) -> list[Chunk]:
    """Cut a text into chunks of about ``chunk_words`` words (from the learner's
    concentration profile). Cuts fall at line ends, so a verse is never split; a
    single very long line is split at punctuation."""
    lines: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        lines.extend(_SENTENCE_BREAK.split(line) if _word_count(line) > chunk_words * 1.5 else [line])

    chunks: list[Chunk] = []
    current: list[str] = []
    for line in lines:
        current.append(line)
        if _word_count(" ".join(current)) >= chunk_words:
            chunks.append(Chunk(len(chunks), "\n".join(current), _word_count(" ".join(current))))
            current = []
    if current:
        # A short tail joins the previous chunk rather than standing alone.
        tail = "\n".join(current)
        if chunks and _word_count(tail) < chunk_words / 2:
            chunks[-1].text += f"\n{tail}"
            chunks[-1].words += _word_count(tail)
        else:
            chunks.append(Chunk(len(chunks), tail, _word_count(tail)))
    return chunks


STOP_WORDS = frozenset(
    [
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "de",
        "du",
        "d",
        "l",
        "à",
        "au",
        "aux",
        "en",
        "et",
        "ou",
        "sur",
        "dans",
        "par",
        "pour",
        "que",
        "qui",
        "ne",
        "pas",
        "se",
        "sa",
        "son",
        "ses",
        "il",
        "elle",
        "on",
        "vous",
        "nous",
        "je",
        "tu",
        "me",
        "te",
        "lui",
        "y",
        "a",
        "est",
        "the",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "and",
        "or",
        "is",
        "are",
        "be",
        "it",
        "his",
        "her",
    ]
)


def cue(text: str, level: CueLevel) -> str:
    """Render a chunk at a cue level. Punctuation and line breaks always stay, they carry the rhythm."""
    if level == "read":
        return text
    if level == "recite":
        return re.sub(r"[^\n]+", "…", _WORD_WITH_JOINERS.sub("", text))

    def blank(match: re.Match[str]) -> str:
        word = match.group(0)
        if level == "first-letters":
            return word[0] + "_" * (len(word) - 1)
        is_key = len(word) >= 4 and word.lower() not in STOP_WORDS
        return "_" * len(word) if is_key else word

    return _WORD.sub(blank, text)


def cue_for(card: Card | None, t: ByHeartTuning = DEFAULT_TUNING.by_heart) -> CueLevel:
    """Cues fade as the chunk's memory stabilises (thresholds in tuning.by_heart)."""
    if card is None:
        return "read"
    stability = card.stability or 0
    if stability < t.key_words_from_days:
        return "first-letters"
    if stability < t.recite_from_days:
        return "key-words-blank"
    return "recite"


def by_heart_units(
    text_id: str,
    title: str,
    subject: str,
    chunks: Sequence[Chunk],
    goal_ids: Sequence[str] = (),
    notion_id: str | None = None,
) -> list[KnowledgeUnit]:
    """Units for a text: one per chunk, learned in order, plus chained recitations
    (chunks 1–2, 1–3, … 1–n). The last chain is the whole text."""

    def unit(uid: str, unit_title: str, prerequisites: Sequence[str]) -> KnowledgeUnit:
        return KnowledgeUnit(
            id=uid,
            subject=subject,
            kind="verbatim",
            title=unit_title,
            importance=2,
            prerequisites=prerequisites,
            goal_ids=goal_ids,
            notion_id=notion_id,
            cumulative=True,
        )

    units = [
        unit(f"{text_id}/c{c.index + 1}", f"{title}: part {c.index + 1}", [f"{text_id}/c{c.index}"] if c.index else [])
        for c in chunks
    ]
    for k in range(2, len(chunks) + 1):
        units.append(
            unit(
                f"{text_id}/chain{k}",
                f"{title}: whole text" if k == len(chunks) else f"{title}: parts 1–{k}",
                [f"{text_id}/c{k}", f"{text_id}/chain{k - 1}" if k > 2 else f"{text_id}/c1"],
            )
        )
    return units


@dataclass(frozen=True)
class Box:
    """In fractions of the image (0–1), adjustable in the review inbox."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class FigureLabel:
    """A label on a map or diagram."""

    id: str
    label: str
    box: Box


def figure_units(
    figure_id: str,
    title: str,
    subject: str,
    labels: Sequence[FigureLabel],
    goal_ids: Sequence[str] = (),
    notion_id: str | None = None,
) -> list[KnowledgeUnit]:
    """ "Blank the map": one unit per hidden label, then the whole figure with every label hidden."""
    units = [
        KnowledgeUnit(
            id=f"{figure_id}/{label.id}",
            subject=subject,
            kind="label",
            title=f"{title}: {label.label}",
            goal_ids=goal_ids,
            notion_id=notion_id,
        )
        for label in labels
    ]
    units.append(
        KnowledgeUnit(
            id=f"{figure_id}/all",
            subject=subject,
            kind="label",
            title=f"{title}: every label",
            prerequisites=[u.id for u in units],
            goal_ids=goal_ids,
            notion_id=notion_id,
        )
    )
    return units


@dataclass(frozen=True)
class Recitation:
    ratio: float
    """Share of the expected words recited in order (longest common subsequence)."""
    missing: list[str]
    """Expected words that were missing or out of place, normalised, for grading."""
    missing_at: list[int] = field(default_factory=list)
    """Their positions in recitation_words(expected), to show them as written."""


def _split(s: str) -> list[str]:
    return [w for w in re.split(r"[\W_]+", s.replace("’", " ").replace("'", " ")) if w]


def _tokens(s: str, accents: bool) -> list[str]:
    # Without accents: decompose, then drop the combining marks (é -> e).
    s = unicodedata.normalize("NFC", s) if accents else re.sub("[\u0300-\u036f]", "", unicodedata.normalize("NFD", s))
    return _split(s.lower())


def recitation_words(text: str) -> list[str]:
    """The words of a text as written, aligned with what compare_recitation() compares."""
    return _split(unicodedata.normalize("NFC", text))


def compare_recitation(expected: str, given: str, accents: bool = False) -> Recitation:
    """Compare a recitation (typed, or a speech transcript in audio mode) with the
    text, word by word and in order. Accents count when spelling is the point."""
    a = _tokens(expected, accents)
    b = _tokens(given, accents)
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    missing: list[str] = []
    missing_at: list[int] = []
    i = j = 0
    while i < len(a):
        if j < len(b) and a[i] == b[j]:
            i += 1
            j += 1
        elif j < len(b) and dp[i][j + 1] >= dp[i + 1][j]:
            j += 1
        else:
            missing.append(a[i])
            missing_at.append(i)
            i += 1
    return Recitation(dp[0][0] / len(a) if a else 1.0, missing, missing_at)


def recitation_attempt(r: Recitation, latency_ms: float, t: ByHeartTuning = DEFAULT_TUNING.by_heart) -> Attempt:
    """Turn a recitation into an attempt for grading: near-perfect is correct, close is a near miss."""
    correct = r.ratio >= t.pass_ratio
    return Attempt(correct=correct, near_miss=not correct and r.ratio >= t.near_miss_ratio, latency_ms=latency_ms, level="recall")
