import pytest

from engine_helpers import NOW, studied, unit
from lc_engine import ItemState, KnowledgeMap, MemoryModel, Notion, PlacementCheck, Rating, notion_status

MATHS = KnowledgeMap.load("maths-core")


def test_rejects_unknown_prerequisites_and_cycles():
    with pytest.raises(ValueError):
        KnowledgeMap([Notion("a", "A", "x", prerequisites=["b"])])
    with pytest.raises(ValueError):
        KnowledgeMap([Notion("a", "A", "x", prerequisites=["b"]), Notion("b", "B", "x", prerequisites=["a"])])


def test_turns_a_flagged_gap_into_a_path_missing_prerequisites_first():
    known = {"whole-numbers", "multiplication-facts", "order-of-operations", "fractions-meaning"}
    path = [n.id for n in MATHS.learning_path(["linear-equations"], known.__contains__)]
    assert path[-1] == "linear-equations"
    assert path.index("negative-numbers") < path.index("linear-equations")
    assert path.index("algebraic-expressions") < path.index("linear-equations")
    assert "whole-numbers" not in path, "known notions are skipped"


def test_places_a_learner_on_a_chain_in_a_handful_of_questions():
    chain = KnowledgeMap(Notion(f"n{i}", f"N{i}", "x", prerequisites=[f"n{i - 1}"] if i else []) for i in range(16))
    knows_up_to = 9  # truth: n0..n9 known, n10..n15 not
    check = PlacementCheck(chain, [n.id for n in chain.all])
    while (n := check.next()) is not None:
        check.record(n.id, int(n.id[1:]) <= knows_up_to)
    r = check.result()
    assert r.asked <= 5, f"asked {r.asked}"
    assert len(r.known) == 10
    assert len(r.unknown) == 6


def test_reads_a_notion_status_from_the_memories_of_its_units():
    memory = MemoryModel()
    solid = studied(unit("a"), [Rating.Good] * 4, 15, 1)
    shaky = studied(unit("b"), [Rating.Hard], 1, 12)
    assert notion_status([ItemState(unit("x"))], memory, NOW) == "not-started"
    assert notion_status([solid], memory, NOW) == "solid"
    assert notion_status([solid, shaky], memory, NOW) == "fragile"
