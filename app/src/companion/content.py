"""Sample content for the phone test, so both use cases work offline on day one.

Use case 1: the first verses of *Le Corbeau et le Renard*, to learn by heart.
Use case 2: "Passé simple", as if parents had pushed it; in the real flow the
server writes the lesson (lc_ingest.teach_notion) and a parent accepts it in
the review inbox.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lc_engine import KnowledgeUnit, by_heart_units, chunk_text

CORBEAU_TITLE = "Le Corbeau et le Renard"
CORBEAU = """Maître Corbeau, sur un arbre perché,
Tenait en son bec un fromage.
Maître Renard, par l'odeur alléché,
Lui tint à peu près ce langage :
« Hé ! bonjour, Monsieur du Corbeau.
Que vous êtes joli ! que vous me semblez beau !
Sans mentir, si votre ramage
Se rapporte à votre plumage,
Vous êtes le Phénix des hôtes de ces bois. »"""


@dataclass(frozen=True)
class Question:
    """One way to ask a unit. Several per unit, so practice varies (lc_engine.pick_probe)."""

    id: str
    level: str  # recognize | recall | apply
    prompt: str
    answer: str
    choices: tuple[str, ...] = ()


@dataclass
class Content:
    units: list[KnowledgeUnit] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    """Verbatim text of each by-heart unit."""
    questions: dict[str, list[Question]] = field(default_factory=dict)
    """Questions of each practice unit."""
    missions: dict[str, tuple[str, str, list[str]]] = field(default_factory=dict)
    """mission id -> (kind, title, unit ids)."""


def _q(uid: str, n: int, level: str, prompt: str, answer: str, *choices: str) -> Question:
    return Question(f"{uid}#{n}", level, prompt, answer, tuple(choices))


PASSE_SIMPLE: list[tuple[KnowledgeUnit, list[Question]]] = [
    (
        KnowledgeUnit("ps/er", "French", "rule", "Passé simple of -er verbs", 3, notion_id="passe-simple"),
        [
            _q("ps/er", 1, "recognize", "chanter, ils …", "chantèrent", "chantèrent", "chantirent", "chantaient"),
            _q("ps/er", 2, "recall", "parler, je …", "parlai"),
            _q("ps/er", 3, "recall", "marcher, nous …", "marchâmes"),
            _q("ps/er", 4, "recall", "donner, elle …", "donna"),
            _q("ps/er", 5, "recall", "aimer, vous …", "aimâtes"),
        ],
    ),
    (
        KnowledgeUnit("ps/ir", "French", "rule", "Passé simple of -ir verbs (finir)", 2, ["ps/er"], notion_id="passe-simple"),
        [
            _q("ps/ir", 1, "recognize", "finir, nous …", "finîmes", "finîmes", "finâmes", "finissions"),
            _q("ps/ir", 2, "recall", "choisir, il …", "choisit"),
            _q("ps/ir", 3, "recall", "grandir, ils …", "grandirent"),
            _q("ps/ir", 4, "recall", "réussir, tu …", "réussis"),
        ],
    ),
    (
        KnowledgeUnit(
            "ps/etre-avoir", "French", "fact", "Passé simple of être and avoir", 3, ["ps/er"], notion_id="passe-simple"
        ),
        [
            _q("ps/etre-avoir", 1, "recognize", "être, il …", "fut", "fut", "était", "eut"),
            _q("ps/etre-avoir", 2, "recall", "avoir, ils …", "eurent"),
            _q("ps/etre-avoir", 3, "recall", "être, nous …", "fûmes"),
            _q("ps/etre-avoir", 4, "recall", "avoir, j' …", "eus"),
        ],
    ),
]


def sample_content(chunk_words: int) -> Content:
    """``chunk_words`` comes from the learner's concentration profile."""
    content = Content()
    chunks = chunk_text(CORBEAU, chunk_words)
    corbeau = by_heart_units("corbeau", CORBEAU_TITLE, "French", chunks, notion_id="fables")
    for unit in corbeau:
        part = unit.id.rsplit("/", 1)[1]  # c3 = part 3; chain3 = parts 1-3
        if part.startswith("chain"):
            content.texts[unit.id] = "\n".join(c.text for c in chunks[: int(part[5:])])
        else:
            content.texts[unit.id] = chunks[int(part[1:]) - 1].text
    content.units += corbeau
    content.missions["by-heart:corbeau"] = ("by-heart", CORBEAU_TITLE, [u.id for u in corbeau])

    for unit, questions in PASSE_SIMPLE:
        content.units.append(unit)
        content.questions[unit.id] = questions
    content.missions["pushed:passe-simple"] = ("pushed", "Passé simple", [u.id for u, _ in PASSE_SIMPLE])
    return content
