import { State, type Card } from 'ts-fsrs';
import { addDays, startOfDay } from './time.ts';
import type { ItemState } from './types.ts';

/**
 * Several short sessions a day, each finite. A unit learned or missed in one
 * session comes back for a second look in a later one (same-day steps in the
 * memory model); everything else is due on a day, not at a minute.
 */
export function isDue(card: Card, now: Date): boolean {
  if (card.state === State.Learning || card.state === State.Relearning) return card.due.getTime() <= now.getTime();
  return card.due.getTime() < addDays(startOfDay(now), 1).getTime();
}

export interface DayRules {
  sessionsPerDay: number;
  minGapMinutes: number;
}

export interface DaySoFar {
  sessionsDone: number;
  lastEndedAt?: Date;
}

export type SessionGate = { open: true } | { open: false; reason: string; nextAt: Date };

/** May a session start now? The family sets the ceiling; a break between sessions is part of learning. */
export function sessionGate(now: Date, rules: DayRules, today: DaySoFar): SessionGate {
  if (today.sessionsDone >= rules.sessionsPerDay) {
    return { open: false, reason: `That's all ${rules.sessionsPerDay} sessions for today.`, nextAt: addDays(startOfDay(now), 1) };
  }
  if (today.lastEndedAt) {
    const nextAt = new Date(today.lastEndedAt.getTime() + rules.minGapMinutes * 60_000);
    if (nextAt.getTime() > now.getTime()) {
      return { open: false, reason: 'A break between sessions helps memory.', nextAt };
    }
  }
  return { open: true };
}

/**
 * When will a session next have something worth doing? Used when today's plan
 * is empty, so the app says "come back at 18:30" instead of offering filler.
 */
export function nextUsefulTime(items: readonly ItemState[], now: Date): Date | undefined {
  let best: Date | undefined;
  for (const { card } of items) {
    if (!card) continue;
    if (isDue(card, now)) return now;
    const at = card.state === State.Learning || card.state === State.Relearning ? card.due : startOfDay(card.due);
    if (!best || at < best) best = at;
  }
  return best;
}
