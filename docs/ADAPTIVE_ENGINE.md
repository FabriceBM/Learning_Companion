# Adaptive engine

How the app decides **what** each person reviews, **when**, **how hard**, and **whether to remind them**. The code is in [`packages/engine`](../packages/engine); this document explains the choices.

```
npm install
npm test           # 28 tests: engine + extraction schema
npm run simulate   # 60-day comparison with two synthetic learners
```

## 1. Memory model: FSRS-6

Each unit has a memory state for each learner:

* **Stability S**: the number of days after which recall falls to 90%.
* **Difficulty D**: from 1 to 10.
* **Retrievability R**: the probability of recall right now.

Recall decays with a power-law forgetting curve:

$$R(t, S) = \left(1 + f\,\frac{t}{S}\right)^{-w_{20}},\qquad f = 0.9^{-1/w_{20}} - 1$$

After each answer, S and D are updated by the FSRS-6 equations: 21 weights $w_0 \dots w_{20}$, including a learnable decay $w_{20}$. The next interval is the time until R falls to the **target retention** $r^*$:

$$I = \frac{S}{f}\left({r^*}^{-1/w_{20}} - 1\right)$$

**Why FSRS:** it is the strongest open scheduler on the public [srs-benchmark](https://github.com/open-spaced-repetition/srs-benchmark), which measures recall prediction on real review logs. It beats SM-2 (Anki's legacy scheduler) and HLR (the half-life regression model Duolingo published in 2016). It is maintained by its authors, and it has a TypeScript scheduler (`ts-fsrs`) and a Rust optimizer with a WASM binding, so both can run on a phone.

**Personalisation:** `fitWeights()` runs the reference optimizer (fsrs-rs) on one learner's review log.
* **Defaults first:** below 400 reviews (`MIN_REVIEWS_TO_FIT`), the learner uses population defaults. A planned improvement is family or age-group defaults as an intermediate step.
* **Refit:** weekly, overnight.
* **Replay:** after a refit, memory states are rebuilt by replaying the review log, which is the source of truth.
* **Speed:** about one second for a few thousand reviews.

> Not yet in the code: separate weights per *kind* of knowledge (vocabulary vs. methods) once a learner has enough data for each. FSRS supports this through per-preset parameters.

## 2. Grading: objective, never self-rated

Children are not asked to rate their own recall: "Easy" is the fastest way out of a session. `gradeAttempt()` maps what happened onto the four FSRS grades:

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

The same unit is asked in harder forms as its memory stabilises (`probeLevelFor()`):

| Stability | Level | Example (procedure: adding fractions) |
|---|---|---|
| < 3 days | recognise | pick 7/8 among four answers |
| 3–10 days | recall | 3/4 + 1/8 = ? |
| 10–30 days | apply | a fresh generated exercise: 2/5 + 3/10 = ? |
| ≥ 30 days | explain | why isn't 3/4 + 1/8 equal to 4/12? |

The top of the ladder depends on the kind of knowledge: a date stops at *recall*, a concept goes up to *explain*. Multiple choice never earns "Easy", because picking an answer is easier than producing it.

## 4. Goals: how high to aim

`targetRetention()` sets $r^*$ for each unit. Above about 0.9, the review load grows steeply for little gain, so 0.9 is the default.

| Situation | Target |
|---|---|
| Default | 0.90 |
| Foundational unit (others build on it) | 0.92 |
| Nice to know | 0.85 |
| A test this unit counts for is within 7 days | 0.95 |
| One-off material whose tests are all past (e.g. a history chapter) | 0.80, kept alive cheaply |
| Cumulative material after its test (times tables, conjugations) | back to its normal target |

**Test-aware scheduling** (`AdaptiveScheduler.fitToGoal`): suppose the normal interval would jump past a test, and predicted recall on test day would be below 0.95. Then the review is pulled forward to 1–2 days before the test, so there is a night of sleep between the last review and the test. Test dates also decide which new material is introduced first.

**Workload control** (`relaxForLoad`): if the work needed keeps exceeding the agreed budget (more than 110% on average over a week), everyday targets go down a little, never below 0.80. Test targets are not touched. This prevents the "347 reviews due" avalanche.

## 5. Session planner

`planSession()` builds a finite list that fits the budget:

1. **Due reviews, most at risk first.** Priority is
   $$\text{importance} \times \text{test boost} \times \max(0.01,\; r^* - R + 0.05)$$
   where the test boost grows linearly from 1 to 2 over the last 7 days before a test.
2. **New units only if every due review fits.** They are capped per day and throttled by recent accuracy: none below 70%, half between 70% and 80%. A unit is introduced only when its prerequisites have R ≥ 0.8, and material for the nearest test comes first.
3. **Order:**
   * open on a unit the child almost certainly knows (warm-up);
   * interleave subjects ([Rohrer & Taylor, 2007](ARCHITECTURE.md#references)): telling apart "which method is this?" is part of the skill;
   * close on a likely success, so the session ends on a good note.
4. **Deferred reviews** stay due and are re-prioritised tomorrow. The count is used for workload control and is never shown to the child.

`SessionRunner` then adapts inside the session:
* a missed unit returns once at the end (successive relearning); the retry is not sent to the memory model;
* after 3 misses in a row it slips in an easier unit;
* after 5 it ends kindly;
* it stops when the budget is used, even with items left;
* the child can always stop.

Each planned item carries a `why` line, for example *"Seen 6 days ago · recall now about 78% · Maths test in 4 days"*. It is shown under "Why this card?", so the schedule is never a black box.

## 6. Reminders: designed to make themselves unnecessary

`decideNudge()` answers: should today's reminder be sent, and when?

**Hard rules, checked in this order:**
1. Reminders switched off (`maxPerDay` = 0).
2. Today's session already done.
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

## 7. Planned: concept graph and re-teaching

Not implemented yet; this is the design:

* **Leech handling:** a unit with 4 or more lapses triggers a check of its prerequisites. Weak prerequisites are scheduled first.
* **Re-teaching instead of drilling:** offer a new explanation, a worked example or a mnemonic generated by the extraction model, or a "teach-back" moment with a parent.
* **Splitting:** a unit that bundles two ideas is split into two.
* **Skill estimates:** knowledge tracing over the prerequisite graph gives a skill-level mastery estimate for the family view.

## 8. Simulation

`npm run simulate` runs 60 days with:
* 4 subjects, one lesson per subject per week, 12 units each: 432 units in total;
* 5 tests;
* a 10-minute daily budget, Sundays off, and about 10% of other days missed at random.

Two synthetic learners have hidden FSRS-6 memories: A forgets fast, B has a strong memory. Their hidden memory decides every answer. Three schedulers get the same budget and the same new-material limit:

* **Fixed ladder:** intervals of 1-2-4-7-14-30-60 days, back to the start on a miss. This is how Leitner boxes and many apps work.
* **FSRS, population weights:** FSRS with default weights, no knowledge of tests.
* **Adaptive:** this engine, with weights refitted on days 14, 28 and 42 and aware of tests.

Output of the current code:

```
┌────────────────────┬──────────────────────────────────┬─────────┬───────────────┬─────────────────────┬────────────┬─────────────────────────────┐
│ learner            │ policy                           │ min/day │ units studied │ recall on test days │ worst test │ all units, recall at day 60 │
├────────────────────┼──────────────────────────────────┼─────────┼───────────────┼─────────────────────┼────────────┼─────────────────────────────┤
│ A: forgets fast    │ Fixed ladder                     │ 8.2     │ 254           │ 48%                 │ 24%        │ 56%                         │
│ A: forgets fast    │ FSRS, population weights         │ 6.8     │ 288           │ 52%                 │ 37%        │ 60%                         │
│ A: forgets fast    │ Adaptive (personal + test-aware) │ 7.8     │ 275           │ 89%                 │ 77%        │ 59%                         │
│ B: strong memory   │ Fixed ladder                     │ 7.9     │ 264           │ 51%                 │ 25%        │ 60%                         │
│ B: strong memory   │ FSRS, population weights         │ 6.8     │ 346           │ 64%                 │ 57%        │ 76%                         │
│ B: strong memory   │ Adaptive (personal + test-aware) │ 7.1     │ 329           │ 93%                 │ 79%        │ 73%                         │
└────────────────────┴──────────────────────────────────┴─────────┴───────────────┴─────────────────────┴────────────┴─────────────────────────────┘

Personalisation (adaptive engine):
┌────────────────────┬─────────────────────────────┬──────────────────────────────┬────────────────────────────┐
│ learner            │ mean interval, mature units │ log loss, population weights │ log loss, personal weights │
├────────────────────┼─────────────────────────────┼──────────────────────────────┼────────────────────────────┤
│ A: forgets fast    │ 31.4 days                   │ 0.421                        │ 0.414                      │
│ B: strong memory   │ 48.1 days                   │ 0.291                        │ 0.295                      │
└────────────────────┴─────────────────────────────┴──────────────────────────────┴────────────────────────────┘
```

**What this shows:**
* **Test days:** about 90% recall on test days instead of 48–64%, in a similar or smaller amount of time. The gain comes from knowing the tests: test material is introduced first and reviews are pulled to just before the test.
* **Long-term recall:** day-60 recall over all units is about the same as plain FSRS (59 vs 60% for A, 73 vs 76% for B). Effort moves toward what is tested; it is not created from nothing.
* **The fixed ladder** spends the most time and does worst on every measure. It over-reviews what a strong memory already holds and under-reviews what a fast forgetter loses.
* **Per-learner frequency:** mature units come back about every 31 days for A and every 48 days for B.

**What it does not show:**
* **Personal weights barely changed prediction quality here** (log loss 0.421 → 0.414 for A, 0.291 → 0.295 for B). Each unit's own memory state already absorbs most of the difference between these synthetic children. Per-user fitting does help on real review data in the public benchmark, so it stays, but it has to prove itself on this family's own logs. That is why log loss is logged per learner from day one.
* **The learners are synthetic** and follow the same equations the scheduler assumes, which flatters FSRS-based schedulers. Real children have bad days, guess, and learn outside the app. The simulation tests the mechanics, not the effect size.

## 9. Code map

| File | Responsibility |
|---|---|
| `types.ts` | Knowledge units, goals, learner profile, attempts |
| `memory.ts` | FSRS-6 wrapper: recall now, next due date for a target retention |
| `grading.ts` | Attempt → grade; question ladder |
| `retention.ts` | Target retention policy, workload relaxation |
| `scheduler.ts` | Memory + goals: test-aware due dates |
| `planner.ts` | Today's finite session |
| `session.ts` | In-session adaptation and stopping rules |
| `nudge.ts` | Reminder policy |
| `personalize.ts` | Per-learner weight fitting (fsrs-rs) |
| `scripts/simulate.ts` | 60-day comparison |
