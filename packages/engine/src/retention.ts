import { DEFAULT_TUNING, type Tuning } from './tuning.ts';
import type { Goal, KnowledgeUnit } from './types.ts';
import { daysBetween } from './time.ts';

/**
 * Target probability of recall when a unit comes back. This is the main dial
 * between "remember more" and "spend less time". Values: tuning.ts.
 */
export type RetentionPolicy = Tuning['retention'];

export const DEFAULT_RETENTION: RetentionPolicy = DEFAULT_TUNING.retention;

/** The soonest test still ahead that this unit counts for. */
export function nextGoal(ku: KnowledgeUnit, goals: readonly Goal[], now: Date): Goal | undefined {
  return goals
    .filter((g) => ku.goalIds.includes(g.id) && g.date.getTime() > now.getTime())
    .sort((a, b) => a.date.getTime() - b.date.getTime())[0];
}

export function targetRetention(
  ku: KnowledgeUnit,
  goals: readonly Goal[],
  now: Date,
  policy: RetentionPolicy = DEFAULT_RETENTION,
): number {
  const goal = nextGoal(ku, goals, now);
  if (goal && daysBetween(now, goal.date) <= policy.testWindowDays) return policy.test;
  if (!goal && ku.goalIds.length > 0 && !ku.cumulative) return policy.maintenance;
  if (ku.importance === 3) return policy.foundational;
  if (ku.importance === 1) return policy.niceToKnow;
  return policy.base;
}

/**
 * When the work needed keeps exceeding the agreed time budget, aim a little
 * lower instead of piling up a backlog. Test targets are left alone.
 *
 * @param overload average (minutes needed / minutes budgeted) over the last week
 */
export function relaxForLoad(
  policy: RetentionPolicy,
  overload: number,
  workload: Tuning['workload'] = DEFAULT_TUNING.workload,
): RetentionPolicy {
  if (overload <= workload.overloadThreshold) return policy;
  const drop = Math.min(workload.maxDrop, (overload - 1) * workload.dropPerOverload);
  const floor = (value: number) => Math.max(policy.maintenance, value - drop);
  return {
    ...policy,
    base: floor(policy.base),
    foundational: floor(policy.foundational),
    niceToKnow: floor(policy.niceToKnow),
  };
}
