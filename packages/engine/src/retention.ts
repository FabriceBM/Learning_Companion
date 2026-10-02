import type { Goal, KnowledgeUnit } from './types.ts';
import { daysBetween } from './time.ts';

/**
 * Target probability of recall when a unit comes back. This is the main dial
 * between "remember more" and "spend less time": above ~0.9 the review load
 * grows steeply for little gain.
 */
export interface RetentionPolicy {
  base: number;
  /** Importance 3: other units build on it. */
  foundational: number;
  /** Importance 1. */
  niceToKnow: number;
  /** Days before a test during which its units aim higher. */
  testWindowDays: number;
  test: number;
  /** One-off material whose tests are all past: kept alive cheaply. */
  maintenance: number;
}

export const DEFAULT_RETENTION: RetentionPolicy = {
  base: 0.9,
  foundational: 0.92,
  niceToKnow: 0.85,
  testWindowDays: 7,
  test: 0.95,
  maintenance: 0.8,
};

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
export function relaxForLoad(policy: RetentionPolicy, overload: number): RetentionPolicy {
  if (overload <= 1.1) return policy;
  const drop = Math.min(0.06, (overload - 1) * 0.05);
  const floor = (value: number) => Math.max(policy.maintenance, value - drop);
  return {
    ...policy,
    base: floor(policy.base),
    foundational: floor(policy.foundational),
    niceToKnow: floor(policy.niceToKnow),
  };
}
