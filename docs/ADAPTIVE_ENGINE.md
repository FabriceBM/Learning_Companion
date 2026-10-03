# Adaptive engine

How the app decides **what** each person reviews, **when**, **how hard**, and **whether to remind them**. The code is in [`packages/engine`](../packages/engine); this document explains the choices.

```
uv sync                                    # Python 3.12+, installs the engine, ingest and server packages
uv run pytest                              # 445 tests: engine behaviour, the language-neutral spec, extraction, server, app logic
uv run packages/engine/scripts/simulate.py # 60-day comparison with two synthetic learners
uv run packages/engine/scripts/push.py     # use case 2 end to end: parents push a notion → placement check → path → mission → one day of sessions
uv run packages/engine/scripts/params.py   # regenerate docs/PARAMETERS.md from the code
```

Every number in this document is a parameter with a default, a range and a reason: see [PARAMETERS.md](PARAMETERS.md).

## 1. Memory model: FSRS-6

Each unit has a memory state for each learner:

* **Stability S**: the number of days after which recall falls to 90%.
* **Difficulty D**: from 1 to 10.
* **Retrievability R**: the probability of recall right now.

Recall decays with a power-law forgetting curve:

$$R(t, S) = \left(1 + f\,\frac{t}{S}\right)^{-w_{20}},\qquad f = 0.9^{-1/w_{20}} - 1$$

After each answer, S and D are updated by the FSRS-6 equations: 21 weights $w_0 \dots w_{20}$, including a learnable decay $w_{20}$. The next interval is the time until R falls to the **target retention** $r^*$:

$$I = \frac{S}{f}\left({r^*}^{-1/w_{20}} - 1\right)$$

**Why FSRS:** it is the strongest open scheduler on the public [srs-benchmark](https://github.com/open-spaced-repetition/srs-benchmark), which measures recall prediction on real review logs. It beats SM-2 (Anki's legacy scheduler) and HLR (the half-life regression model Duolingo published in 2016). It is maintained by its authors, who publish both pieces the engine uses: the Python scheduler [`py-fsrs`](https://github.com/open-spaced-repetition/py-fsrs) (pure Python, so it runs on the phone) and the Rust optimizer [`fsrs-rs`](https://github.com/open-spaced-repetition/fsrs-rs) through its Python binding `fsrs-rs-python` (the one Anki uses; on the server).

**Personalisation:** `fit_weights()` runs the reference optimizer (fsrs-rs) on one learner's review log.
* **Defaults first:** below 400 reviews (`MIN_REVIEWS_TO_FIT`), the learner uses population defaults. A planned intermediate step is defaults fitted per age band on the family's pooled reviews: a 10-year-old and a parent are unlikely to share one forgetting curve.
* **Refit:** weekly, overnight.
* **Replay:** after a refit, memory states are rebuilt by replaying the review log, which is the source of truth.
* **Speed:** about one second for a few thousand reviews.

> Not yet in the code: separate weights per *kind* of knowledge (vocabulary vs. methods) once a learner has enough data for each. FSRS supports this through per-preset parameters.

## 2. Grading: objective, never self-rated

Children are not asked to rate their own recall: "Easy" is the fastest way out of a session. `grade_attempt()` maps what happened onto the four FSRS grades:

| What happened | Grade |
|---|---|
| Wrong | Again |
| Right with a hint, or a near miss (typo when spelling is not the point) | Hard |
| Right, but slower than this child's 75th percentile, or the child tapped "not sure" | Hard |
| Right, faster than this child's 25th percentile, tapped "sure", and not a multiple-choice question | Easy |
| Otherwise right | Good |

* **Near misses depend on the unit.** For a dictation or accent rule, *a* vs *à* is a real miss. For the meaning of a Spanish word, a missing accent is a near miss.
* **The optional sure / not-sure tap does two jobs.** It refines grading, and it trains calibration: confident errors followed by feedback are corrected especially well ([Butterfield & Metcalfe, 2001](ARCHITECTURE.md#references)).

## 3. Question ladder: desirable difficulty

The same unit is asked in harder forms as its memory stabilises (`probe_level_for()`):

| Stability | Level | Example (procedure: adding fractions) |
|---|---|---|
| < 3 days | recognise | pick 7/8 among four answers |
| 3–10 days | recall | 3/4 + 1/8 = ? |
| 10–30 days | apply | a fresh generated exercise: 2/5 + 3/10 = ? |
| ≥ 30 days | explain | why isn't 3/4 + 1/8 equal to 4/12? |

The top of the ladder depends on the kind of knowledge: a date stops at *recall*, a concept goes up to *explain*. Multiple choice never earns "Easy", because picking an answer is easier than producing it.

## 4. Goals: how high to aim

`target_retention()` sets $r^*$ for each unit. Above about 0.9, the review load grows steeply for little gain, so 0.9 is the default.

| Situation | Target |
|---|---|
| Default | 0.90 |
| Foundational unit (others build on it) | 0.92 |
| Nice to know | 0.85 |
| A test this unit counts for is within 7 days | 0.95 |
| One-off material whose tests are all past (e.g. a history chapter) | 0.80, kept alive cheaply |
| Cumulative material after its test (times tables, conjugations) | back to its normal target |

**Test-aware scheduling** (`AdaptiveScheduler._fit_to_goal`): suppose the normal interval would jump past a test, and predicted recall on test day would be below 0.95. Then the review is pulled forward to 1–2 days before the test, so there is a night of sleep between the last review and the test. Test dates also decide which new material is introduced first.

**Workload control** (`relax_for_load`): if the work needed keeps exceeding the agreed time (more than 110% on average over a week), everyday targets go down a little, never below 0.80. Test targets are not touched. This prevents the "347 reviews due" avalanche.

## 5. Session planner: mixed review

`plan_session()` builds one finite session that fits the session length. Without a mission it is a mixed review:

1. **Due reviews, most at risk first.** Priority is
   $$\text{importance} \times \text{test boost} \times \max(0.01,\; r^* - R + 0.05)$$
   where the test boost grows linearly from 1 to 2 over the last 7 days before a test.
2. **New units only if every due review fits.** They are capped per day and throttled by recent accuracy: none below 70%, half between 70% and 80%. A unit is introduced only when its prerequisites have R ≥ 0.8, and material for the nearest test comes first.
3. **Order:**
   * open on a unit the child almost certainly knows (warm-up);
   * interleave subjects ([Rohrer & Taylor, 2007](ARCHITECTURE.md#references)): telling apart "which method is this?" is part of the skill;
   * close on a likely success, so the session ends on a good note.
4. **Deferred reviews** stay due and are re-prioritised in the next session. The count is used for workload control and is never shown to the child.

`SessionRunner` then adapts inside the session:
* a missed unit returns once at the end (successive relearning); the retry is not sent to the memory model;
* after 3 misses in a row it slips in an easier unit;
* after 5 it ends kindly;
* it stops when the session length is used, even with items left;
* the child can always stop.

Each planned item carries a `why` line, for example *"Seen 6 days ago · recall now about 78% · Maths test in 4 days"*. It is shown under "Why this card?", so the schedule is never a black box.

## 6. Missions: the learner chooses, the session focuses

`missions.py` defines five kinds of mission: **by-heart** (a text or figure to learn word for word, use case 1), **pushed** (a notion parents pushed and its missing prerequisites, use case 2), **test** (units a dated test covers), **topic** (anything chosen freely) and **mixed** ("keep everything fresh").

**Suggestions.** `suggest_missions()` ranks missions; the learner can pick any of them.
* **Test:** scored by $b + (1 - \text{readiness}) \times \min(1, \text{window} / \text{days left})$, where readiness is the mean predicted recall on the test day and $b$ is 0.5 inside the test window (0.2 outside), so a close test leads.
* **Pushed notion:** $0.6 \times$ the share of units not yet secure; **by heart:** $0.5 \times$ that share.
* **Topic:** $0.3 \times$ that share.
* **Mixed review:** $0.7 \times \text{due} / (\text{due} + 15)$, so it rises as reviews pile up without overtaking a close test.

Any mission with a date (a recitation, "before September") is scored like a test.

**A mission session** (`planSession({ focus })`) goes entirely to the mission:
1. **Repair:** prerequisites of mission units with recall below `mission.repair_below_recall` (0.8), foundations first.
2. **Due mission reviews,** most at risk first.
3. **New mission units** in prerequisite order. A unit may follow a prerequisite *of the same notion* introduced earlier in the session, so a notion is learned in one go. A prerequisite from another notion must already be known.
4. **Extra practice** on mission units whose stability is below `mission.secure_stability_days` (7), lowest recall first, until the session is full.

**Order and focus:**
* **Order:** repairs first, then by depth in the prerequisite graph, one notion at a time, ending on a likely success.
* **Blocked inside a mission:** practising one notion at a time suits a skill being acquired. Mixed review interleaves, which helps discrimination and long-term retention ([Brunmair & Richter, 2019](ARCHITECTURE.md#references)).
* **Other due reviews wait:** they are counted in `plan.waiting`, and a day's wait costs little.
* **Full focus by default:** `mission.focus_share` (default 1) can reserve part of the session for the most at-risk other reviews. With full focus, a small mission makes a short session; it is never padded.

**Progress.** `mission_progress()` reports units started, units secure, and readiness on the test day. A unit is secure at a stability of 7 days. That needs correct answers on separate days, which is successive relearning, not one good session. A mission is complete when every unit is secure; its units then return to normal spaced reviews.

## 7. Several sessions a day

`day.py`, with limits per age band in `profiles.py`: up to 5 sessions of 10–15 minutes, default 2, at least 90 minutes apart for a child.

* **Same-day second looks.** `MemoryModel` with `same_day_gap_minutes` turns on FSRS-6 short-term steps equal to the break:
  * a new unit gets two same-day steps;
  * a missed unit gets one;
  * a unit answered correctly moves on to its normal spaced schedule.

  FSRS-6 models these short-term reviews itself (weights $w_{17}$–$w_{19}$). Weights are refitted with `fitWeights(log, { sameDayReviews: true })`.
* **What is due:** `is_due()` treats units in a same-day step as due at their exact time, and everything else as due for the whole day. A morning session therefore takes the day's reviews, and a later one takes the second looks.
* **Shared limits:** the new-unit limit is shared across the day's sessions (`new_today`).
* **The gate:** `session_gate()` refuses a session before the break is over or after the daily number. `next_useful_time()` tells the app when a session will next have something worth doing, so it never offers filler.
* **The worked example** in [ARCHITECTURE.md §2.2](ARCHITECTURE.md#22-use-case-2-parents-push-a-notion) shows three sessions of one day on a pushed notion.

## 8. Reminders: designed to make themselves unnecessary

`decide_nudge()` answers: should today's reminder be sent, and when?

**Hard rules, checked in this order:**
1. Reminders switched off (`max_per_day` = 0).
2. A session already done today (later sessions start on the child's initiative).
3. Nothing planned.
4. Rest day.
5. Daily cap reached (1 by default).

**Self-start pause:** if the child started on their own on at least 80% of active days over the last 14 days (with at least 7 active days), reminders pause. *The habit has formed, and the reminder has done its job.* Habit automaticity takes weeks to months ([Lally et al., 2010](ARCHITECTURE.md#references)), so the pause is checked continuously.

**Back-off, never escalation:**
* after 3 ignored reminders in a row, remind every other day at most;
* after 6, stop reminding the child, and the parent sees it in the weekly summary.

The opposite pattern, louder and guiltier reminders when ignored, is exactly what this charter rules out.

**Choosing the time slot:** Thompson sampling over the slots the family agreed on (e.g. "after school 17:00–18:30", "Saturday morning"). Each slot keeps a Beta(1 + reminders followed by a session within 30 min, 1 + reminders ignored) posterior. The slot with the highest sampled value wins, so the app learns that one child does better before dinner than straight after school.

**Text:** what to do and how long, starting with the child's own plan (an implementation intention, [Gollwitzer, 1999](ARCHITECTURE.md#references)): *"After my snack: 9 min today (Spanish, Maths)."* A test checks every reminder against a banned list: streak, lose, sad, miss, hurry, last chance, exclamation marks.

**What the research on nudges says, and what we take from it:**
* **Mixed but real effects:** nudges in education are cheap and often help, but effects vary a lot between settings and fade when they become noise ([Damgaard & Nielsen, 2018](ARCHITECTURE.md#references)). Large nudge programmes for older students have shown little effect ([Oreopoulos & Petronijevic, 2019](ARCHITECTURE.md#references)). Hence one reminder at most, and fewer over time.
* **Informing parents works well:** regular, specific information sent to parents improved children's outcomes, both for school assignments ([Bergman & Chan, 2021](ARCHITECTURE.md#references)) and early literacy ([York, Loeb & Doss, 2019](ARCHITECTURE.md#references)). Hence the weekly summary, the dinner-table questions, and telling parents rather than escalating on the child.
* **Same bandit, different goal:** Duolingo optimises its reminders with a bandit that maximises return to the app ([Yancey & Settles, 2020](ARCHITECTURE.md#references)). We use the same kind of bandit for the time slot, but count success as a useful session started, and aim to stop reminding altogether.

## 9. Knowledge map, gaps and placement

`knowledge_map.py`, with a sample map in `maps/maths-core.json` (22 notions from whole numbers to linear functions, Pythagoras and probability).

* **Notions and levels.** A notion lists its prerequisites; the map rejects unknown prerequisites and cycles. A notion's level is its position on the map; where a domain has an absolute scale (CEFR for languages), the notion carries that label.
* **Learning path.** `learningPath(targets, known)` walks down from the pushed notions, stops at known notions, and returns what is missing in prerequisite order. It becomes a pushed mission (use case 2).
* **Varied practice.** `pick_probe()` picks the least recently asked question at the unit's level, falling back to an easier level. A rule practised in free sessions therefore cycles through varied items instead of repeating one.
* **Placement check.** `PlacementCheck` follows Knowledge Space Theory ([Doignon & Falmagne, 1999](ARCHITECTURE.md#references)):
  * passing a notion marks its prerequisites known; missing it marks what builds on it unknown;
  * each question goes to the notion that settles the most notions either way;
  * on a 16-notion chain it places a learner in 4–5 questions (tested), and in the worked example 5 questions settle 10 notions.
  * The results are starting beliefs: once units are practised, their memory states take over.
* **Notion status.** `notion_status()` reads the status from its units' memories: not started, learning, fragile (some unit below 80% recall) or solid (every unit stable for 3 weeks).

**Still planned:**
* **Leech handling:** a unit with 4 or more lapses triggers a check of its prerequisites, then a new explanation, a worked example or a teach-back with a parent, and possibly a split into two units.
* **Skill estimates:** knowledge tracing over the map ([BKT/DKT](ARCHITECTURE.md#references)) to estimate notions never asked directly.

## 10. Learning by heart (use case 1)

`by_heart.py`:
* **`chunkText(text, chunkWords)`** cuts at line ends (a single long line at punctuation) into chunks of about the learner's chunk size; a short tail joins the previous chunk.
* **`cue(text, level)`** renders a chunk at one of four levels: `read` (full text), `first-letters`, `key-words-blank` (content words of 4+ letters hidden) or `recite` (nothing shown, punctuation and line breaks kept for rhythm).
* **`cue_for(card)`** fades the cue as stability grows: first letters after the first meeting, key words blanked from `by_heart.key_words_from_days` (2), recite from `by_heart.recite_from_days` (5).
* **`by_heart_units()`** creates one unit per chunk, learned in order, plus chained units "parts 1–k" that need part k and the previous chain. The last chain is the whole text.
* **`figure_units()`** creates one unit per hidden label of a map or diagram, plus "every label" once each is known.
* **`compare_recitation()`** aligns the recitation with the text word by word, in order (longest common subsequence) and lists the missing words. `recitation_attempt()` maps the result to a grade: ≥ 95% correct, ≥ 85% near miss, otherwise missed.
* **Audio mode (phase 2):** a `listen` step before `read`, and spoken recitation through on-device speech recognition, graded by the same comparison.

## 11. Concentration profile

`concentration.py`. Each value starts at an age default and moves toward the learner's own data, weighted like `concentration.prior_weight` (5) sessions, so a few odd days don't swing it.

| Value | Estimated from | Applied to (`apply_concentration`) |
|---|---|---|
| Attention span | Pooled over sessions: the first minute where accuracy stays 15 points below the start for two minutes, or answer time rises 40% | Session length = min(family limit, span) |
| Chunk size | Largest chunk size whose first study succeeds 70% of the time | `chunk_text` |
| Switch cost | Accuracy right after a subject change versus staying on one subject | Mixed review grouped by subject above `concentration.group_above_switch_cost` (0.15) |
| Best hours | Hours with the highest accuracy (at least 10 answers) | Suggested times and reminder slots |
| Recovery | Shortest break after which a session starts at the usual accuracy | Break between sessions = max(family minimum, recovery) |
| Frustration point | Shortest run of misses after which the next answer is a miss 60% of the time | `session.ease_off_after_misses`, with `stop_after_misses` two later |

The test suite checks that a synthetic learner who loses focus at 7 minutes and 30 points per subject switch gets a span of 6–9 minutes, a switch cost above 0.15, and mixed reviews grouped by subject.

## 12. Simulation

`uv run packages/engine/scripts/simulate.py` runs 60 days with:
* 4 subjects, one lesson per subject per week, 12 units each: 432 units in total;
* 5 tests;
* one 10-minute session a day, Sundays off, and about 10% of other days missed at random.

Two synthetic learners have hidden FSRS-6 memories: A forgets fast, B has a strong memory. Their hidden memory decides every answer. Three schedulers get the same session length and the same new-material limit:

* **Fixed ladder:** intervals of 1-2-4-7-14-30-60 days, back to the start on a miss. This is how Leitner boxes and many apps work.
* **FSRS, population weights:** FSRS with default weights, no knowledge of tests.
* **Adaptive:** this engine, with weights refitted on days 14, 28 and 42 and aware of tests.

Output of the current code:

```
learner           policy                            min/day  units studied  recall on test days  worst test  all units, recall at day 60
----------------  --------------------------------  -------  -------------  -------------------  ----------  ---------------------------
A: forgets fast   Fixed ladder                      8.2      254            48%                  24%         56%
A: forgets fast   FSRS, population weights          7.4      299            53%                  38%         62%
A: forgets fast   Adaptive (personal + test-aware)  7.8      291            89%                  76%         62%
B: strong memory  Fixed ladder                      7.9      264            51%                  25%         60%
B: strong memory  FSRS, population weights          6.9      331            62%                  53%         73%
B: strong memory  Adaptive (personal + test-aware)  7.3      341            93%                  79%         76%

Personalisation (adaptive engine; weights refitted on days 14, 28, 42):
learner           mean interval, mature units  log loss, population weights  log loss, personal weights
----------------  ---------------------------  ----------------------------  --------------------------
A: forgets fast   29.9 days                    0.430                         0.430
B: strong memory  46.4 days                    0.315                         0.314
```

The first (TypeScript) engine gave nearly the same table (test days 84–93% adaptive, 54–64% plain FSRS, 48–51% fixed ladder). The small differences come from the two FSRS libraries rounding intervals slightly differently.

**What this shows:**
* **Test days:** about 90% recall on test days instead of 48–62%, in a similar amount of time. The gain comes from knowing the tests: test material is introduced first and reviews are pulled to just before the test.
* **Long-term recall:** day-60 recall over all units is the same as plain FSRS (62 vs 62% for A, 76 vs 73% for B). Effort moves toward what is tested; it is not created from nothing.
* **The fixed ladder** spends the most time and does worst on every measure. It over-reviews what a strong memory already holds and under-reviews what a fast forgetter loses.
* **Per-learner frequency:** mature units come back about every 30 days for A and every 46 days for B.

**What it does not show:**
* **Personal weights barely changed prediction quality here** (log loss 0.430 → 0.430 for A, 0.315 → 0.314 for B). Each unit's own memory state already absorbs most of the difference between these synthetic children. Per-user fitting does help on real review data in the public benchmark, so it stays, but it has to prove itself on this family's own logs. That is why log loss is logged per learner from day one.
* **The learners are synthetic** and follow the same equations the scheduler assumes, which flatters FSRS-based schedulers. Real children have bad days, guess, and learn outside the app. The simulation tests the mechanics, not the effect size.

## 13. Code map

All in `packages/engine/src/lc_engine/` unless noted: plain Python, no I/O, the current time passed in, so the same code runs on the phone and on the server.

| File | Responsibility |
|---|---|
| `model.py` | Knowledge units, goals, learner profile, attempts |
| `memory.py` | FSRS-6 wrapper: recall now, next due date for a target retention |
| `grading.py` | Attempt → grade; question ladder; varied question rotation |
| `retention.py` | Target retention policy, workload relaxation |
| `scheduler.py` | Memory + goals: test-aware due dates |
| `planner.py` | One finite session: mixed review, or a focused mission |
| `missions.py` | Mission kinds, scope, progress, ranked suggestions |
| `day.py` | Several sessions a day: what is due now, the gate between sessions, the next useful time |
| `knowledge_map.py` | Notions and prerequisites, learning path for a gap, placement check, notion status |
| `by_heart.py` | Use case 1: chunks, fading cues, chained recitations, blanked maps, recitation grading |
| `concentration.py` | Concentration profile: age defaults, estimation from sessions, application to sessions |
| `tuning.py` | Every parameter: default, range, reason; `with_tuning()` for overrides |
| `session.py` | In-session adaptation and stopping rules |
| `nudge.py` | Reminder policy |
| `personalize.py` | Per-learner weight fitting (fsrs-rs) |
| `profiles.py` | Age bands (10–11, 12–13, parents): session length, sessions per day, break, limits on reminders and new material, answer modes, who sees progress |
| `maps/maths-core.json`, `maps/french-core.json` | Sample knowledge maps (domain › area › notion) |
| `packages/engine/spec/*.json` | The language-neutral spec: 364 input → output cases any implementation of the engine must pass (recorded from the first, TypeScript engine) |
| `packages/engine/scripts/simulate.py` | 60-day comparison |
| `packages/engine/scripts/push.py` | Use case 2 end to end |
| `packages/engine/scripts/params.py` | Generates docs/PARAMETERS.md |
