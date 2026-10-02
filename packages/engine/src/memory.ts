import { createEmptyCard, default_w, forgetting_curve, fsrs, State, type Card, type FSRS, type Grade } from 'ts-fsrs';
import { daysBetween } from './time.ts';

/**
 * One learner's memory model (FSRS-6).
 *
 * It answers two questions: "how likely is this child to recall the unit right
 * now?" and "after this answer, when should we ask again so that recall is
 * still at the target probability?". The weights start at population defaults
 * and are refitted to the child's own review history (see personalize.ts).
 */
export class MemoryModel {
  private readonly schedulers = new Map<number, FSRS>();

  constructor(readonly weights: readonly number[] = default_w) {}

  /** Probability of recall at `at`; 0 for a unit never studied. */
  retrievability(card: Card | undefined, at: Date): number {
    if (!card || card.state === State.New || !card.last_review) return 0;
    const elapsed = Math.max(0, daysBetween(card.last_review, at));
    return forgetting_curve(this.weights, elapsed, card.stability);
  }

  /** Apply one graded answer. The next due date aims for recall = `retention`. */
  review(card: Card | undefined, at: Date, grade: Grade, retention: number): Card {
    return this.scheduler(retention).next(card ?? createEmptyCard(at), at, grade).card;
  }

  private scheduler(retention: number): FSRS {
    const key = Math.round(retention * 100) / 100;
    let scheduler = this.schedulers.get(key);
    if (!scheduler) {
      scheduler = fsrs({
        w: [...this.weights],
        request_retention: key,
        // Same-day retries are handled by the session, not by the long-term model.
        enable_short_term: false,
        // Spreads due dates so a lesson learned in one go doesn't all fall due on one day.
        enable_fuzz: true,
        maximum_interval: 365,
      });
      this.schedulers.set(key, scheduler);
    }
    return scheduler;
  }
}
