import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { decideNudge, recordNudgeOutcome, seededRng, type DayRecord, type NudgeSettings, type NudgeState } from '../src/index.ts';

const settings: NudgeSettings = {
  windows: [
    { id: 'after-school', label: 'After school', days: [1, 2, 3, 4, 5], start: '17:00', end: '18:30' },
    { id: 'evening', label: 'Before dinner', days: [1, 2, 3, 4, 5], start: '18:30', end: '19:30' },
    { id: 'saturday', label: 'Saturday morning', days: [6], start: '10:00', end: '12:00' },
  ],
  maxPerDay: 1,
  restDays: [0],
  intention: 'After my snack',
};

const friday = new Date('2026-10-02T16:00:00');
const sunday = new Date('2026-10-04T16:00:00');
const fresh: NudgeState = { windows: {}, ignoredStreak: 0, days: [] };
const ctx = { sessionDoneToday: false, remindersSentToday: 0, plan: { minutes: 9, subjects: ['Spanish', 'Maths'] }, rng: seededRng(1) };

function days(n: number, f: (i: number) => Partial<DayRecord>): DayRecord[] {
  return Array.from({ length: n }, (_, i) => ({ date: `d${i}`, sessionDone: true, selfStarted: false, nudged: true, ...f(i) }));
}

describe('decideNudge', () => {
  it('sends one informational reminder inside an agreed slot', () => {
    const d = decideNudge(friday, settings, fresh, ctx);
    assert.equal(d.send, true);
    if (!d.send) return;
    assert.ok(['after-school', 'evening'].includes(d.windowId));
    assert.ok(d.at.getHours() >= 17);
    assert.equal(d.text, 'After my snack: 9 min today (Spanish, Maths).');
  });

  it('never uses guilt, streaks or urgency', () => {
    const d = decideNudge(friday, { ...settings, intention: undefined }, fresh, ctx);
    assert.ok(d.send);
    if (d.send) assert.doesNotMatch(d.text, /streak|lose|lost|sad|miss|hurry|last chance|don't break|!/i);
  });

  it('stays silent when the session is done, on rest days, or at the daily limit', () => {
    assert.equal(decideNudge(friday, settings, fresh, { ...ctx, sessionDoneToday: true }).send, false);
    assert.equal(decideNudge(sunday, settings, fresh, ctx).send, false);
    assert.equal(decideNudge(friday, settings, fresh, { ...ctx, remindersSentToday: 1 }).send, false);
  });

  it('pauses once the child starts on their own', () => {
    const state = { ...fresh, days: days(10, (i) => ({ selfStarted: i !== 3, nudged: false })) };
    const d = decideNudge(friday, settings, state, ctx);
    assert.equal(d.send, false);
    if (!d.send) assert.match(d.reason, /Habit formed/);
  });

  it('backs off, then stops, when reminders are ignored', () => {
    const backoff = { ...fresh, ignoredStreak: 3, days: days(3, () => ({ sessionDone: false })) };
    assert.equal(decideNudge(friday, settings, backoff, ctx).send, false);
    const stopped = { ...fresh, ignoredStreak: 6 };
    assert.equal(decideNudge(friday, settings, stopped, ctx).send, false);
  });

  it('learns which slot works for this child', () => {
    let state = fresh;
    for (let i = 0; i < 12; i++) {
      state = recordNudgeOutcome(state, 'evening', true);
      state = recordNudgeOutcome(state, 'after-school', false);
    }
    state = { ...state, ignoredStreak: 0 };
    const rng = seededRng(7);
    const picks = Array.from({ length: 50 }, () => decideNudge(friday, settings, state, { ...ctx, rng }));
    const evening = picks.filter((d) => d.send && d.windowId === 'evening').length;
    assert.ok(evening >= 45, `evening picked ${evening}/50`);
  });
});
