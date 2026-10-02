import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { Rating } from 'ts-fsrs';
import { MemoryModel, SessionRunner, planSession, type ItemState } from '../src/index.ts';
import { NOW, learner, studied, unit } from './helpers.ts';

const memory = new MemoryModel();
const subjects = ['Maths', 'Spanish', 'History'];

/** 60 units reviewed ~a week ago with short intervals, so they are all due. */
function backlog(): ItemState[] {
  return Array.from({ length: 60 }, (_, i) =>
    studied(unit(`u${i}`, { subject: subjects[i % 3]! }), [Rating.Hard, Rating.Hard], 1, 6),
  );
}

describe('planSession', () => {
  it('never exceeds the time budget and reports what it deferred', () => {
    const plan = planSession({ learner: learner({ sessionMinutes: 5 }), items: backlog(), goals: [], now: NOW, memory });
    const seconds = plan.items.reduce((s, i) => s + i.seconds, 0);
    assert.ok(seconds <= 5 * 60);
    assert.ok(plan.deferred > 0);
    assert.equal(plan.items.filter((i) => i.kind === 'new').length, 0, 'no new material while reviews are deferred');
  });

  it('interleaves subjects', () => {
    const plan = planSession({ learner: learner({ sessionMinutes: 8 }), items: backlog(), goals: [], now: NOW, memory });
    for (let i = 2; i < plan.items.length; i++) {
      const run = plan.items.slice(i - 2, i + 1).map((p) => p.subject);
      assert.ok(new Set(run).size > 1, `three ${run[0]} in a row at ${i}`);
    }
  });

  it('opens and closes on units the child probably knows', () => {
    const plan = planSession({ learner: learner({ sessionMinutes: 8 }), items: backlog(), goals: [], now: NOW, memory });
    const recalls = plan.items.filter((i) => i.kind === 'review').map((i) => i.recall).sort((a, b) => b - a);
    assert.equal(plan.items[0]!.recall, recalls[0]);
    assert.equal(plan.items.at(-1)!.recall, recalls[1]);
  });

  it('waits for prerequisites before introducing a unit', () => {
    const base = unit('fractions-equivalent');
    const next = unit('fractions-add', { prerequisites: ['fractions-equivalent'] });
    const plan = planSession({ learner: learner(), items: [{ ku: base }, { ku: next }], goals: [], now: NOW, memory });
    assert.deepEqual(plan.items.map((i) => i.kuId), ['fractions-equivalent']);
  });

  it('introduces nothing new when the child is struggling', () => {
    const items = Array.from({ length: 5 }, (_, i) => ({ ku: unit(`n${i}`) }));
    const plan = planSession({ learner: learner({ recentAccuracy: 0.6 }), items, goals: [], now: NOW, memory });
    assert.equal(plan.items.length, 0);
  });
});

describe('SessionRunner', () => {
  const plan = planSession({ learner: learner({ sessionMinutes: 6 }), items: backlog(), goals: [], now: NOW, memory });
  const wrong = { correct: false, latencyMs: 6000, hintsUsed: 0, level: 'recall' as const };

  it('ends kindly after a run of misses', () => {
    const runner = new SessionRunner(plan, 600);
    let step = runner.next();
    while (step.type === 'ask') {
      runner.answer(step.item, wrong, 10, step.retry);
      step = runner.next();
    }
    assert.equal(step.reason, 'ease-off');
    assert.equal(runner.results.length, 5);
  });

  it('slips in the easiest remaining unit after three misses', () => {
    const runner = new SessionRunner(plan, 600);
    for (let i = 0; i < 3; i++) {
      const step = runner.next();
      assert.equal(step.type, 'ask');
      if (step.type === 'ask') runner.answer(step.item, wrong, 10, step.retry);
    }
    const asked = new Set(runner.results.map((r) => r.item.kuId));
    const easiest = Math.max(...plan.items.filter((i) => !asked.has(i.kuId)).map((i) => i.recall));
    const step = runner.next();
    assert.ok(step.type === 'ask' && step.item.recall === easiest);
  });

  it('stops when the time budget is used, even with items left', () => {
    const runner = new SessionRunner(plan, 30);
    let step = runner.next();
    while (step.type === 'ask') {
      runner.answer(step.item, { ...wrong, correct: true }, 12, step.retry);
      step = runner.next();
    }
    assert.equal(step.reason, 'time-budget');
  });
});
