import { sampleBeta, type Rng } from './random.ts';

/** A time slot the family agreed on, e.g. "after school", weekdays 17:00-18:30. */
export interface NudgeWindow {
  id: string;
  label: string;
  /** 0 = Sunday ... 6 = Saturday */
  days: number[];
  start: string; // "HH:MM"
  end: string;
}

export interface NudgeSettings {
  windows: NudgeWindow[];
  /** Hard cap, 1 by default. 0 switches reminders off. */
  maxPerDay: number;
  /** No reminders at all on these days. */
  restDays: number[];
  /** The child's own plan ("After my snack"), used as the reminder's first words. */
  intention?: string;
}

export interface DayRecord {
  date: string; // YYYY-MM-DD
  sessionDone: boolean;
  /** Started without a reminder. */
  selfStarted: boolean;
  nudged: boolean;
}

export interface NudgeState {
  /** Per window: reminders followed by a session within 30 minutes, and ignored ones. */
  windows: Record<string, { started: number; ignored: number }>;
  ignoredStreak: number;
  /** Most recent last. */
  days: DayRecord[];
}

export type NudgeDecision =
  | { send: false; reason: string }
  | { send: true; at: Date; windowId: string; text: string; reason: string };

export const NUDGE_RULES = {
  /** Reminders pause once the child starts on their own on this share of active days... */
  selfStartShare: 0.8,
  /** ...measured over this many recent days... */
  lookbackDays: 14,
  /** ...with at least this many active days. */
  minActiveDays: 7,
  /** After this many ignored reminders in a row, remind every other day only. */
  backoffAfterIgnored: 3,
  /** After this many, stop reminding the child; parents see it in the weekly summary. */
  stopAfterIgnored: 6,
} as const;

export interface NudgeContext {
  sessionDoneToday: boolean;
  remindersSentToday: number;
  plan: { minutes: number; subjects: string[] };
  rng?: Rng;
}

/**
 * Decide whether to send today's reminder, and when.
 *
 * The goal is for reminders to become unnecessary: they pause when the child
 * starts on their own, back off when ignored, and never escalate. The time slot
 * is learned per child with Thompson sampling over the agreed windows.
 */
export function decideNudge(now: Date, settings: NudgeSettings, state: NudgeState, ctx: NudgeContext): NudgeDecision {
  const no = (reason: string): NudgeDecision => ({ send: false, reason });

  if (settings.maxPerDay <= 0) return no('Reminders are switched off.');
  if (ctx.sessionDoneToday) return no("Today's session is already done.");
  if (ctx.plan.minutes === 0) return no('Nothing planned today.');
  if (settings.restDays.includes(now.getDay())) return no('Rest day.');
  if (ctx.remindersSentToday >= settings.maxPerDay) return no('Daily reminder limit reached.');

  const active = state.days.slice(-NUDGE_RULES.lookbackDays).filter((d) => d.sessionDone);
  const selfStarted = active.filter((d) => d.selfStarted).length;
  if (active.length >= NUDGE_RULES.minActiveDays && selfStarted / active.length >= NUDGE_RULES.selfStartShare) {
    return no('Habit formed: started on their own on most days, so reminders pause.');
  }
  if (state.ignoredStreak >= NUDGE_RULES.stopAfterIgnored) {
    return no('Reminders were ignored several times in a row: stopped. Parents see it in the weekly summary.');
  }
  if (state.ignoredStreak >= NUDGE_RULES.backoffAfterIgnored && state.days.at(-1)?.nudged) {
    return no('Backing off after ignored reminders: none today.');
  }

  const minutesNow = now.getHours() * 60 + now.getMinutes();
  const open = settings.windows.filter((w) => w.days.includes(now.getDay()) && toMinutes(w.end) > minutesNow);
  if (open.length === 0) return no('No agreed time slot left today.');

  const rng = ctx.rng ?? Math.random;
  const scored = open.map((w) => {
    const s = state.windows[w.id] ?? { started: 0, ignored: 0 };
    return { w, score: sampleBeta(1 + s.started, 1 + s.ignored, rng) };
  });
  const best = scored.reduce((a, b) => (b.score > a.score ? b : a));

  const at = new Date(now);
  const start = Math.max(minutesNow, toMinutes(best.w.start));
  at.setHours(Math.floor(start / 60), start % 60, 0, 0);

  return {
    send: true,
    at,
    windowId: best.w.id,
    text: reminderText(settings.intention, ctx.plan),
    reason: `Slot "${best.w.label}" chosen from this child's past responses.`,
  };
}

/** Update what we learned about a slot once we know whether the reminder was followed. */
export function recordNudgeOutcome(state: NudgeState, windowId: string, started: boolean): NudgeState {
  const s = state.windows[windowId] ?? { started: 0, ignored: 0 };
  return {
    ...state,
    windows: {
      ...state.windows,
      [windowId]: started ? { ...s, started: s.started + 1 } : { ...s, ignored: s.ignored + 1 },
    },
    ignoredStreak: started ? 0 : state.ignoredStreak + 1,
  };
}

/**
 * Informational and finite: what, how long, nothing else. No mascot guilt, no
 * streak threats, no fake urgency.
 */
export function reminderText(intention: string | undefined, plan: { minutes: number; subjects: string[] }): string {
  const what = `${plan.minutes} min today (${plan.subjects.join(', ')})`;
  return intention ? `${intention}: ${what}.` : `${what[0]!.toUpperCase()}${what.slice(1)}.`;
}

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}
