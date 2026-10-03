"""Knowledge measured on an absolute map, not by school grade.

A notion is one idea or skill ("adding fractions with different
denominators"); it lists the notions it builds on. Any curriculum, a parent's
judgement ("our eldest lacks this before high school") or a photographed lesson
just points at notions on the same map.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from importlib import resources
from typing import Literal

from .memory import MemoryModel
from .model import ItemState


@dataclass(frozen=True)
class Notion:
    id: str
    title: str
    domain: str
    """Domain › area › notion, e.g. French › Conjugation › Passé simple."""
    area: str | None = None
    prerequisites: Sequence[str] = ()
    level: str | None = None
    """Optional absolute level label where the domain has one, e.g. CEFR "A2" for languages."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "prerequisites", tuple(self.prerequisites))


def _sort_key(title: str) -> tuple[str, str]:
    """Alphabetical as people read it: accents and case don't move a title."""
    plain = "".join(c for c in unicodedata.normalize("NFD", title) if not unicodedata.combining(c))
    return plain.casefold(), title


class KnowledgeMap:
    def __init__(self, notions: Iterable[Notion]) -> None:
        self._notions: dict[str, Notion] = {}
        for n in notions:
            self._notions[n.id] = n
        for n in self._notions.values():
            for p in n.prerequisites:
                if p not in self._notions:
                    raise ValueError(f"{n.id}: unknown prerequisite {p}")
        for n in self._notions.values():
            if n.id in self.ancestors(n.id):
                raise ValueError(f"{n.id}: prerequisite cycle")

    @classmethod
    def load(cls, name: str) -> KnowledgeMap:
        """A map shipped with the engine: "maths-core", "french-core"."""
        return cls(load_notions(name))

    def get(self, notion_id: str) -> Notion:
        try:
            return self._notions[notion_id]
        except KeyError:
            raise KeyError(f"Unknown notion {notion_id}") from None

    @property
    def all(self) -> list[Notion]:
        return list(self._notions.values())

    def ancestors(self, notion_id: str) -> dict[str, None]:
        """Everything this notion builds on, transitively (in discovery order)."""
        out: dict[str, None] = {}
        stack = list(self.get(notion_id).prerequisites)
        while stack:
            p = stack.pop()
            if p in out:
                continue
            out[p] = None
            stack.extend(self.get(p).prerequisites)
        return out

    def descendants(self, notion_id: str) -> dict[str, None]:
        """Everything that builds on this notion, transitively."""
        return {n.id: None for n in self._notions.values() if notion_id in self.ancestors(n.id)}

    def depth(self, notion_id: str) -> int:
        """Length of the longest prerequisite chain below a notion: 0 for foundations."""
        prerequisites = self.get(notion_id).prerequisites
        return 1 + max(self.depth(p) for p in prerequisites) if prerequisites else 0

    def learning_path(self, targets: Sequence[str], known: Callable[[str], bool]) -> list[Notion]:
        """What to learn to reach the targets: the missing targets plus their
        missing prerequisites, foundations first. This is how a flagged gap becomes a plan."""
        needed: dict[str, None] = {}
        # Walk down from the targets; a known notion stops the walk (what it builds on is known too).
        stack = list(targets)
        while stack:
            nid = stack.pop()
            if nid in needed or known(nid):
                continue
            needed[nid] = None
            stack.extend(self.get(nid).prerequisites)
        return sorted((self.get(nid) for nid in needed), key=lambda n: (self.depth(n.id), _sort_key(n.title)))


@cache
def _load_raw(name: str) -> str:
    return resources.files("lc_engine.maps").joinpath(f"{name}.json").read_text(encoding="utf-8")


def load_notions(name: str) -> list[Notion]:
    return [Notion(**n) for n in json.loads(_load_raw(name))]


Belief = Literal["known", "unknown", "unsure"]


@dataclass(frozen=True)
class PlacementResult:
    known: list[str]
    unknown: list[str]
    unsure: list[str]
    asked: int


class PlacementCheck:
    """Short placement check (after Knowledge Space Theory, the idea behind ALEKS):
    one question can settle many notions. Passing a notion makes its prerequisites
    likely known; failing it makes what builds on it likely unknown. Each question
    goes to the notion that settles the most either way.

    The results are starting beliefs, not verdicts: the memory model takes over as
    soon as the units are practised, and a notion marked known but failed later
    simply comes back as a gap.
    """

    def __init__(self, knowledge_map: KnowledgeMap, scope: Iterable[str], max_questions: int = 12) -> None:
        self._map = knowledge_map
        self._max_questions = max_questions
        self._belief: dict[str, Belief] = {nid: "unsure" for nid in scope}
        self._asked = 0

    def next(self) -> Notion | None:
        """The most informative notion to ask about next, or None when done."""
        if self._asked >= self._max_questions:
            return None
        best: tuple[str, int, int] | None = None
        for nid, belief in self._belief.items():
            if belief != "unsure":
                continue
            if_pass = 1 + self._count_unsure(self._map.ancestors(nid))
            if_fail = 1 + self._count_unsure(self._map.descendants(nid))
            score = min(if_pass, if_fail)
            depth = self._map.depth(nid)
            if best is None or score > best[1] or (score == best[1] and depth < best[2]):
                best = (nid, score, depth)
        return self._map.get(best[0]) if best else None

    def record(self, notion_id: str, passed: bool) -> None:
        self._asked += 1
        spread = self._map.ancestors(notion_id) if passed else self._map.descendants(notion_id)
        for nid in (notion_id, *spread):
            if nid in self._belief:
                self._belief[nid] = "known" if passed else "unknown"

    def result(self) -> PlacementResult:
        def by(belief: Belief) -> list[str]:
            return [nid for nid, b in self._belief.items() if b == belief]

        return PlacementResult(by("known"), by("unknown"), by("unsure"), self._asked)

    def _count_unsure(self, ids: Iterable[str]) -> int:
        return sum(1 for nid in ids if self._belief.get(nid) == "unsure")


NotionStatus = Literal["not-started", "learning", "fragile", "solid"]


def notion_status(
    units: Sequence[ItemState],
    memory: MemoryModel,
    now: datetime,
    fragile_below: float = 0.8,
    solid_from_days: float = 21,
) -> NotionStatus:
    """A notion's status from the memories of its units: solid when every unit is
    stable for weeks, fragile when any studied unit has slipped below the line."""
    studied = [u for u in units if u.card is not None]
    if not studied:
        return "not-started"
    if any(memory.retrievability(u.card, now) < fragile_below for u in studied):
        return "fragile"
    if len(studied) == len(units) and all((u.card.stability or 0) >= solid_from_days for u in studied if u.card):
        return "solid"
    return "learning"
