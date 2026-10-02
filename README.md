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

A family learning companion, like Duolingo for everyone at home but without the compulsion loop. Photograph a lesson; it becomes small units of knowledge with questions; each person reviews in short sessions that end, scheduled for their own memory and their next tests. Success is measured as knowledge kept per minute, not time in the app, and the reminders are designed to make themselves unnecessary.

| | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The proposal: system, flows for the four use cases, data model, stack, privacy, roadmap, **open questions** |
| [docs/ADAPTIVE_ENGINE.md](docs/ADAPTIVE_ENGINE.md) | How frequencies adapt to each person: FSRS-6 memory model, test-aware targets, session planner, reminder policy, simulation |
| [docs/CHARTER.md](docs/CHARTER.md) | Calm-by-design rules: what replaces streaks, guilt reminders, hearts, gems and leagues |
| [prototype/index.html](prototype/index.html) | Clickable sample of the phone app (open it in a browser) |
| [packages/engine](packages/engine) | The adaptive engine in TypeScript, with tests and a 60-day simulation |
| [packages/ingest](packages/ingest) | Lesson photo → units and questions with the Claude API |

```bash
npm install
npm test            # engine + extraction schema tests
npm run simulate    # adaptive vs. fixed-ladder vs. plain FSRS, two synthetic learners, 60 days
```
