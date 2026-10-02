import type { Card, Grade } from 'ts-fsrs';
import { MemoryModel } from './memory.ts';
import { DEFAULT_RETENTION, nextGoal, targetRetention, type RetentionPolicy } from './retention.ts';
import { addDays, daysBetween, maxDate, startOfDay } from './time.ts';
import type { Goal, ItemState } from './types.ts';

/**
 * Decides when each unit comes back for one learner: the memory model gives the
 * interval for the unit's target retention, then test dates can pull it earlier.
 */
export class AdaptiveScheduler {
  constructor(
    readonly memory: MemoryModel,
    readonly goals: readonly Goal[],
    readonly policy: RetentionPolicy = DEFAULT_RETENTION,
  ) {}

  /** Apply one graded answer and return the unit's new memory state and due date. */
  record(item: ItemState, at: Date, grade: Grade): Card {
    const target = targetRetention(item.ku, this.goals, at, this.policy);
    const card = this.memory.review(item.card, at, grade, target);
    const goal = nextGoal(item.ku, this.goals, at);
    return goal ? this.fitToGoal(card, goal) : card;
  }

  /**
   * If the normal interval would jump past a test and recall on test day would
   * be below the test target, bring the review forward to 1-2 days before the
   * test. A night of sleep between the last review and the test helps.
   */
  private fitToGoal(card: Card, goal: Goal): Card {
    if (card.due.getTime() <= goal.date.getTime()) return card;
    if (this.memory.retrievability(card, goal.date) >= this.policy.test) return card;

    const reviewedAt = card.last_review ?? card.due;
    const lead = daysBetween(reviewedAt, goal.date) >= 3 ? 2 : 1;
    const due = maxDate(addDays(reviewedAt, 1), addDays(startOfDay(goal.date), -lead));
    // The test is tomorrow morning: today's review was the last useful one.
    if (due.getTime() >= goal.date.getTime()) return card;
    return { ...card, due, scheduled_days: Math.round(daysBetween(reviewedAt, due)) };
  }
}
