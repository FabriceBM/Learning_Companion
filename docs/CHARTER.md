# Calm-by-design charter

This is a family Duolingo without the compulsion loop. Each rule below names an engagement pattern, says why it works against learning or wellbeing, and says what we do instead. Rules marked **[tested]** are enforced by automated tests in `packages/engine`, so they cannot regress silently.

## The patterns we refuse

| Engagement pattern | Why it hurts | What we do instead |
|---|---|---|
| **Streaks with loss aversion** ("Don't lose your 87-day streak!") | Turns learning into anxiety about losing; children do the minimum to keep the counter alive; one sick day brings guilt | A weekly rhythm with planned rest days. Skipping a day costs nothing: the plan adapts and nothing is "lost". |
| **Guilt reminders** (a sad mascot, escalating pings) | Uses social and emotional pressure on children; trains them to ignore or resent the app | At most one reminder a day for a child, two for parents who ask **[tested]**, only in agreed time slots **[tested]**, informational wording only **[tested]**. Reminders back off when ignored and pause once the child starts on their own **[tested]**. |
| **Hearts or lives that punish mistakes** | Mistakes are where learning happens; punishing them teaches avoidance and guessing safe | A mistake becomes tomorrow's question, with a short explanation. A confident mistake gets extra feedback, because it is the most correctable kind. |
| **XP, gems, chests, random rewards** | Variable rewards drive compulsion; extrinsic rewards can crowd out interest in the subject ([Deci et al., 1999](ARCHITECTURE.md#references)) | Feedback about the learning itself: what became solid this week, readiness for Tuesday's test, a unit moving from *fragile* to *solid*. |
| **Leagues against strangers** | Social comparison and anxiety; rewards time spent, not learning | Cooperative family goals. No rankings, no strangers. |
| **Infinite lessons, "one more"** | Optimises time in app, not learning; erodes sleep and other activities | Finite sessions of 10–15 minutes **[tested]**, up to the number the family allows per day (at most 5), with a break of at least 90 minutes between them **[tested]**. A session is offered only when it is useful; otherwise the app says when the next one will be **[tested]**. The end screen has no "keep going" button. |
| **Easy repetition to farm points** | Creates an illusion of competence | Desirable difficulty: a question ladder, interleaved subjects in mixed review **[tested]**, and spacing tuned to each person. A mission counts a unit as secure only after correct answers on separate days, never after one good session. |
| **A hidden algorithm** | Dependence; children can't learn how learning works | "Why this card?" on every card. Parents and children see the same information. Every tuning knob is a documented [parameter](PARAMETERS.md). |
| **Fake urgency, upsells, ads** | Manipulation | No ads, no purchases and no countdown timers in the child's interface. |
| **Collecting data to drive engagement** | Children's data used against children | Minimal data, hosted in the EU, photos deleted after extraction, one-tap export and delete. |

## What keeps learners coming back instead

We use Self-Determination Theory, which says lasting motivation comes from three needs:

* **Autonomy.**
  * The child picks the mission: a text to learn by heart, a notion pushed by parents, a test, a topic, or keeping everything fresh. Suggestions are ranked, never imposed.
  * The child picks their own time slot and writes their own plan ("After my snack…").
  * They choose to start, can stop at any time, and accept or edit their own cards.
  * Reminders defer to the child's own initiative.
* **Competence.**
  * Sessions are no longer than the child's measured attention span, and by-heart chunks no bigger than what sticks on first study (concentration profile).
  * Difficulty is calibrated so most answers succeed. A target recall of about 0.9 keeps sessions mostly successful while still stretching; learning tends to be fastest at a success rate around 85% ([Wilson et al., 2019](ARCHITECTURE.md#references)).
  * Progress is shown as knowledge: what is solid, what is ready for the test.
  * Sessions open and close on likely successes **[tested]**.
  * After a run of misses the session gets easier, then ends kindly **[tested]**.
* **Relatedness.**
  * Dinner-table questions, teach-back with a parent, and siblings learning together.
  * Parents learn too, alongside their children.

## Limits, by age

The children are 10 to 13; parents learn too. Parents and the child set the child's limits together, and they stay inside the limits of the child's age band, which the engine enforces **[tested]**:

| Setting | Children 10–11 | Children 12–13 | Parents |
|---|---|---|---|
| One session, default (range) | 10 min (5–15) | 12 min (5–15) | 15 min (5–30) |
| Sessions per day, default (range) | 2 (1–5) | 2 (1–5) | 2 (1–5) |
| Break between sessions, at least | 90 min | 90 min | 60 min |
| Reminders per day, at most | 1 | 1 | 2 |
| Who sees progress | parents and child, same view | parents and child, same view | only the parent |

The full list of settings and engine parameters is in [PARAMETERS.md](PARAMETERS.md).

For everyone: rest days (Sunday by default), reminder slots that never fall after bedtime, and a holiday mode that pauses new material and keeps only light maintenance.

## How we know we are keeping our word

These are the guardrails from [Architecture §11](ARCHITECTURE.md#11-what-we-measure-and-what-we-refuse-to-optimise). If any of them is crossed, the parent is told in the weekly summary and the design is revisited:

* sessions are started when nothing useful is due (a sign the app has become a habit for its own sake);
* more than 10% of a child's sessions end by "ease-off";
* the share of sessions children start on their own falls over a month.

**Success means a child who needs fewer and fewer reminders.**
