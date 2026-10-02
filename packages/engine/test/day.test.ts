import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { Rating } from 'ts-fsrs';
import { AdaptiveScheduler, MemoryModel, nextUsefulTime, planSession, sessionGate, type ItemState } from '../src/index.ts';
import { learner, unit } from './helpers.ts';

const morning = new Date('2026-10-03T09:00:00');
const at = (h: number, m = 0) => new Date(new Date(morning).setHours(h, m, 0, 0));

describe('several sessions a day', () => {
  const rules = { sessionsPerDay: 4, minGapMinutes: 90 };

  it('opens a session only after a break, and only up to the daily number', () => {
    assert.equal(sessionGate(at(9), rules, { sessionsDone: 0 }).open, true);
    const tooSoon = sessionGate(at(10), rules, { sessionsDone: 1, lastEndedAt: at(9, 10) });
    assert.equal(tooSoon.open, false);
    if (!tooSoon.open) assert.deepEqual(tooSoon.nextAt, at(10, 40));
    assert.equal(sessionGate(at(11), rules, { sessionsDone: 1, lastEndedAt: at(9, 10) }).open, true);
    assert.equal(sessionGate(at(20), rules, { sessionsDone: 4, lastEndedAt: at(17) }).open, false);
  });

  it('brings a unit missed in the morning back for a second look later the same day', () => {
    const memory = new MemoryModel(undefined, { sameDayGapMinutes: 90 });
    const scheduler = new AdaptiveScheduler(memory, []);
    const missed: ItemState = { ku: unit('tener', { subject: 'Spanish' }) };
    missed.card = scheduler.record(missed, at(9), Rating.Again);
    const plan = (now: Date) => planSession({ learner: learner({ sessionsPerDay: 4 }), items: [missed], goals: [], now, memory });

    assert.equal(plan(at(10)).items.length, 0, 'not before the break');
    assert.deepEqual(nextUsefulTime([missed], at(10)), at(10, 30));
    assert.deepEqual(plan(at(11)).items.map((i) => i.kuId), ['tener']);
    assert.match(plan(at(11)).items[0]!.why, /earlier today/);
  });

  it('shares the new-unit quota across the day', () => {
    const memory = new MemoryModel();
    const items = Array.from({ length: 10 }, (_, i) => ({ ku: unit(`n${i}`) }));
    const first = planSession({ learner: learner({ maxNewPerDay: 6 }), items, goals: [], now: at(9), memory });
    const later = planSession({ learner: learner({ maxNewPerDay: 6 }), items, goals: [], now: at(15), memory, newToday: 4 });
    assert.equal(first.items.filter((i) => i.kind === 'new').length, 6);
    assert.equal(later.items.filter((i) => i.kind === 'new').length, 2);
  });
});
