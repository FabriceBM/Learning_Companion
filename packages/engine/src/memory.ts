import { createEmptyCard, default_w, forgetting_curve, fsrs, State, type Card, type FSRS, type Grade } from 'ts-fsrs';
import { daysBetween } from './time.ts';
import { DEFAULT_TUNING } from './tuning.ts';

export interface MemoryOptions {
  /** With several sessions a day: a new or missed unit comes back after this break for a second look the same day. */
  sameDayGapMinutes?: number;
  maximumIntervalDays?: number;
}

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

  constructor(
    readonly weights: readonly number[] = default_w,
    readonly options: MemoryOptions = {},
  ) {}

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
      const gap = this.options.sameDayGapMinutes;
      scheduler = fsrs({
        w: [...this.weights],
        request_retention: key,
        // One session a day: retries happen inside the session. Several: FSRS-6
        // models the same-day second look (new unit: two steps; missed unit: one).
        enable_short_term: gap !== undefined,
        learning_steps: gap !== undefined ? [`${gap}m`, `${gap}m`] : [],
        relearning_steps: gap !== undefined ? [`${gap}m`] : [],
        // Spreads due dates so a lesson learned in one go doesn't all fall due on one day.
        enable_fuzz: true,
        maximum_interval: this.options.maximumIntervalDays ?? DEFAULT_TUNING.memory.maximumIntervalDays,
      });
      this.schedulers.set(key, scheduler);
    }
    return scheduler;
  }
}
