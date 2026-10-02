import { computeParameters, FSRSBindingItem, FSRSBindingReview } from '@open-spaced-repetition/binding';
import type { Grade } from 'ts-fsrs';
import { daysBetween, startOfDay } from './time.ts';
import { DEFAULT_TUNING } from './tuning.ts';

/** One graded answer. The review log is the source of truth; memory states are derived from it. */
export interface ReviewRecord {
  kuId: string;
  at: Date;
  grade: Grade;
}

/** Below this, population (or family) defaults predict better than a fit. */
export const MIN_REVIEWS_TO_FIT = DEFAULT_TUNING.memory.minReviewsToFit;

/**
 * Fit FSRS-6 weights to one learner's history with the reference optimizer
 * (fsrs-rs, via its WASI binding). Runs in about a second for a few thousand
 * reviews, so it can run on the server weekly or on a tablet overnight.
 */
export async function fitWeights(
  log: readonly ReviewRecord[],
  options: { minReviews?: number; /** true when the learner has several sessions a day */ sameDayReviews?: boolean } = {},
): Promise<number[] | undefined> {
  if (log.length < (options.minReviews ?? MIN_REVIEWS_TO_FIT)) return undefined;

  const byUnit = new Map<string, ReviewRecord[]>();
  for (const r of log) {
    const list = byUnit.get(r.kuId) ?? [];
    list.push(r);
    byUnit.set(r.kuId, list);
  }

  // One training item per review: the unit's history up to and including it.
  const items: FSRSBindingItem[] = [];
  for (const reviews of byUnit.values()) {
    reviews.sort((a, b) => a.at.getTime() - b.at.getTime());
    const history: FSRSBindingReview[] = [];
    let previous: Date | undefined;
    for (const r of reviews) {
      const deltaDays = previous ? Math.max(0, Math.round(daysBetween(startOfDay(previous), startOfDay(r.at)))) : 0;
      history.push(new FSRSBindingReview(r.grade, deltaDays));
      previous = r.at;
      if (history.length >= 2) items.push(new FSRSBindingItem([...history]));
    }
  }

  return computeParameters(items, { enableShortTerm: options.sameDayReviews ?? false });
}
