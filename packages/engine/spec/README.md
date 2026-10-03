# Engine spec

Language-neutral cases: each JSON file lists inputs and the expected output of an engine function. Any implementation of the engine, in any language, must pass them. They are how a module can later move to another language (Rust, for example) one piece at a time, and be checked against exactly the same behaviour.

* **Recorded from the first engine.** The cases were recorded from the TypeScript engine by `scripts/export-spec.ts` (in git history, next to that engine, in commit d1ea68a), then frozen. The Python engine passes all 364: `uv run pytest packages/engine/tests/test_spec.py`.
* **Times** are UTC instants (ISO 8601); the family's zone is Europe/Paris, which matters for "today" and for reminder slots.
* **Memory states** (`card`) are snapshots: `state` (1 learning, 2 review, 3 relearning), `stability` and `difficulty` (FSRS-6), `due`, `last_review`. A `null` card is a unit never studied.
* **Recall** values were rounded to 8 decimals by the first engine: compare them with a tolerance of 1e-7.
* **Names** are snake_case, as in the Python engine (`retention.test_window_days`).

| File | Covers |
|---|---|
| `rng.json` | Seeded random generator and Beta sampler (reminder slot choice) |
| `tuning.json` | Defaults, ranges, overrides and clamping of the 44 parameters |
| `profiles.json` | Age bands and family limits |
| `day.json` | Session gate, what is due now, next useful time |
| `grading.json` | Answer → grade, question ladder, question rotation |
| `retention.json` | Target recall per unit, workload relaxation |
| `by_heart.json` | Chunking, cues, chained units, blanked figures, recitation grading |
| `knowledge_map.json` | Ancestors, descendants, depth, learning paths, placement checks |
| `planner.json` | Whole session plans: mixed review, missions, repair, practice, new-unit limits |
| `session.json` | In-session adaptation: retries, ease-off, stop, time budget |
| `missions.json` | Mission progress and ranked suggestions; notion status |
| `nudge.json` | Reminder decisions and texts |
| `concentration.json` | Concentration profile: defaults, estimation from session logs, application |
