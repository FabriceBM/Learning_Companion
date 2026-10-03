from engine_helpers import NOW, learner
from lc_engine import (
    AdaptiveScheduler,
    Box,
    FigureLabel,
    ItemState,
    MemoryModel,
    Rating,
    add_days,
    by_heart_units,
    chunk_text,
    compare_recitation,
    cue,
    cue_for,
    figure_units,
    grade_attempt,
    recitation_attempt,
    recitation_words,
)

POEM = """Maître Corbeau, sur un arbre perché,
Tenait en son bec un fromage.
Maître Renard, par l'odeur alléché,
Lui tint à peu près ce langage :
« Hé ! bonjour, Monsieur du Corbeau.
Que vous êtes joli ! que vous me semblez beau ! »"""


def test_cuts_a_text_at_line_ends_into_chunks_of_about_the_learner_size():
    small = chunk_text(POEM, 8)
    large = chunk_text(POEM, 16)
    assert len(small) > len(large)
    assert small[0].text == "Maître Corbeau, sur un arbre perché,\nTenait en son bec un fromage."
    assert all(not c.text.startswith(",") for c in small), "never cuts inside a line"


def test_fades_the_cues_full_text_first_letters_key_words_blanked_nothing():
    line = "Tenait en son bec un fromage."
    assert cue(line, "read") == line
    assert cue(line, "first-letters") == "T_____ e_ s__ b__ u_ f______."
    assert cue(line, "key-words-blank") == "______ en son bec un _______."
    assert cue(line, "recite") == "…"


def test_chooses_the_cue_from_memory_stability():
    scheduler = AdaptiveScheduler(MemoryModel())
    ku = by_heart_units("corbeau", "Le Corbeau", "French", chunk_text(POEM, 8))[0]
    assert cue_for(None) == "read"
    card = scheduler.record(ItemState(ku), NOW, Rating.Good)
    assert cue_for(card) == "key-words-blank"
    card = scheduler.record(ItemState(ku, card), add_days(NOW, 3), Rating.Good)
    assert cue_for(card) == "recite"


def test_chains_chunks_into_longer_recitations_ending_with_the_whole_text():
    units = by_heart_units("corbeau", "Le Corbeau", "French", chunk_text(POEM, 8))
    assert [u.id for u in units] == ["corbeau/c1", "corbeau/c2", "corbeau/c3", "corbeau/chain2", "corbeau/chain3"]
    assert "whole text" in units[-1].title
    assert next(u for u in units if u.id == "corbeau/chain3").prerequisites == ("corbeau/c3", "corbeau/chain2")


def test_grades_a_recitation_word_by_word_in_order():
    line = "Maître Corbeau, sur un arbre perché"
    assert compare_recitation(line, "maitre corbeau sur un arbre perche").ratio == 1
    slip = compare_recitation(line, "Maître Corbeau sur une branche perché")
    assert 0.6 < slip.ratio < 0.95
    assert slip.missing == ["un", "arbre"]
    assert [recitation_words(line)[i] for i in slip.missing_at] == ["un", "arbre"]
    accented = compare_recitation("L'élève récite", "l eleve")
    assert [recitation_words("L'élève récite")[i] for i in accented.missing_at] == ["récite"]
    assert compare_recitation(line, "maitre corbeau sur un arbre perche", accents=True).ratio < 1
    latency = learner().latency_ms
    assert grade_attempt(recitation_attempt(compare_recitation(line, line), 8000), latency) == Rating.Good
    assert grade_attempt(recitation_attempt(slip, 8000), latency) == Rating.Again


def test_blanks_a_map_one_unit_per_label_then_the_whole_map():
    units = figure_units(
        "water-cycle",
        "Water cycle",
        "Science",
        [
            FigureLabel("evaporation", "évaporation", Box(0.1, 0.5, 0.2, 0.08)),
            FigureLabel("condensation", "condensation", Box(0.4, 0.1, 0.2, 0.08)),
        ],
    )
    assert len(units) == 3
    assert units[-1].prerequisites == ("water-cycle/evaporation", "water-cycle/condensation")
