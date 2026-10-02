# Learning_Companion
Help my children reviewing all their classes
Goal of this is to produce a tool that can be used on phone (android, maybe iPhone at some point)/tablet
Use cases:
1/ take pictures of lessons to learn
2/ program a reviewing schedules à la Anki/Duolingo
3/ Manage the learning curve of all concepts/vocabulary/rules (grammar/orthograph/vocabulary : everything seen as a language)
4/ compare lessons to SOTA textbooks/Papers selected to compare/improve

Range of topics/subjects covered very broad. Foreign Language, Mothertongue, Mathematics, Physics, Biology, History, etc.
This project needs a name : will be found with all the users :-)

---

## Proposal (v0)

A family learning companion, like Duolingo for everyone at home but without the compulsion loop, built around two use cases on one engine:

1. **Learn a lesson by heart**: a photographed poem, definition or map is cut into chunks sized for the child, learned with fading cues or blanked labels, and brought back until it can be recited. It is paced by the child's concentration profile; an audio mode comes in phase 2.
2. **Parents push a notion**, e.g. *French › Conjugation › Passé simple*: a quick check of what it builds on, a generated lesson with varied exercises, practised by the child in free sessions.

Both become missions the learner picks, worked through in short, focused sessions, several a day if the family allows, scheduled for their own memory. Knowledge is measured on an absolute map of notions, not by school grade. Success is measured as knowledge kept per minute, not time in the app, and the reminders are designed to make themselves unnecessary.

| | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The proposal, starting with **the two use cases** and the loop they share. Then flows, data model, stack, privacy, roadmap, open questions |
| [docs/ADAPTIVE_ENGINE.md](docs/ADAPTIVE_ENGINE.md) | How it adapts to each person: FSRS-6 memory model, missions, several sessions a day, knowledge map and placement check, learning by heart, concentration profile, reminder policy, simulation |
| [docs/PARAMETERS.md](docs/PARAMETERS.md) | Every tuning knob: default, range, and why (generated from the code) |
| [docs/CHARTER.md](docs/CHARTER.md) | Calm-by-design rules: what replaces streaks, guilt reminders, hearts, gems and leagues |
| [prototype/index.html](prototype/index.html) | Clickable sample of the phone app (open it in a browser) |
| [packages/engine](packages/engine) | The adaptive engine in TypeScript, with tests and a 60-day simulation |
| [packages/ingest](packages/ingest) | Lesson photo → units and questions with the Claude API |

```bash
npm install
npm test            # engine + extraction schema tests
npm run push        # use case 2 end to end: placement check → learning path → mission → one day of sessions
npm run simulate    # adaptive vs. fixed-ladder vs. plain FSRS, two synthetic learners, 60 days
npm run params      # regenerate docs/PARAMETERS.md
```
