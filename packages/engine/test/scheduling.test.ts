import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { Rating } from 'ts-fsrs';
import {
  AdaptiveScheduler,
  DEFAULT_RETENTION,
  MemoryModel,
  addDays,
  daysBetween,
  gradeAttempt,
  probeLevelFor,
  relaxForLoad,
  targetRetention,
  type Goal,
  type ItemState,
} from '../src/index.ts';
import { NOW, learner, studied, unit } from './helpers.ts';

describe('gradeAttempt', () => {
  const profile = learner();
  const base = { correct: true, latencyMs: 5000, hintsUsed: 0, level: 'recall' as const };

  it('wrong answer is Again', () => {
    assert.equal(gradeAttempt({ ...base, correct: false }, profile), Rating.Again);
  });
  it('a hint or a near miss is Hard', () => {
    assert.equal(gradeAttempt({ ...base, hintsUsed: 1 }, profile), Rating.Hard);
    assert.equal(gradeAttempt({ ...base, correct: false, nearMiss: true }, profile), Rating.Hard);
  });
  it('slow for this child is Hard', () => {
    assert.equal(gradeAttempt({ ...base, latencyMs: 12_000 }, profile), Rating.Hard);
  });
  it('fast and sure is Easy, except when picking among choices', () => {
    assert.equal(gradeAttempt({ ...base, latencyMs: 2000, confidence: 'sure' }, profile), Rating.Easy);
    assert.equal(gradeAttempt({ ...base, latencyMs: 2000, confidence: 'sure', level: 'recognize' }, profile), Rating.Good);
  });
});

describe('probeLevelFor', () => {
  it('climbs the ladder as memory stabilises, capped by the kind of knowledge', () => {
    const fragile = studied(unit('a', { kind: 'concept' }), [Rating.Good]).card;
    const solid = studied(unit('b', { kind: 'concept' }), [Rating.Good, Rating.Good, Rating.Good, Rating.Easy], 20).card;
    assert.equal(probeLevelFor('concept', undefined), 'recognize');
    assert.equal(probeLevelFor('concept', fragile), 'recognize');
    assert.equal(probeLevelFor('concept', solid), 'explain');
    assert.equal(probeLevelFor('fact', solid), 'recall');
  });
});

describe('targetRetention', () => {
  const test: Goal = { id: 't1', title: 'History test', date: addDays(NOW, 4) };

  it('aims higher in the week before a test', () => {
    assert.equal(targetRetention(unit('a', { goalIds: ['t1'] }), [test], NOW), DEFAULT_RETENTION.test);
  });
  it('drops one-off material to maintenance after its test', () => {
    const after = addDays(NOW, 10);
    assert.equal(targetRetention(unit('a', { goalIds: ['t1'], cumulative: false }), [test], after), DEFAULT_RETENTION.maintenance);
    assert.equal(targetRetention(unit('b', { goalIds: ['t1'], cumulative: true }), [test], after), DEFAULT_RETENTION.base);
  });
  it('relaxes everyday targets under sustained overload, never tests', () => {
    const relaxed = relaxForLoad(DEFAULT_RETENTION, 1.8);
    assert.ok(relaxed.base < DEFAULT_RETENTION.base);
    assert.ok(relaxed.base >= DEFAULT_RETENTION.maintenance);
    assert.equal(relaxed.test, DEFAULT_RETENTION.test);
  });
});

describe('AdaptiveScheduler', () => {
  it('pulls a review to just before a test when recall would be too low on the day', () => {
    const ku = unit('tener', { goalIds: ['quiz'] });
    const item = studied(ku, [Rating.Good, Rating.Good], 3, 5);
    const free = new AdaptiveScheduler(new MemoryModel(), []).record(item, NOW, Rating.Good);

    // A quiz three quarters of the way into the normal interval, outside the one-week test window.
    const goal: Goal = { id: 'quiz', title: 'Spanish quiz', date: addDays(NOW, 0.75 * daysBetween(NOW, free.due)) };
    assert.ok(daysBetween(NOW, goal.date) > DEFAULT_RETENTION.testWindowDays);
    assert.ok(new MemoryModel().retrievability(free, goal.date) < DEFAULT_RETENTION.test);

    const fitted = new AdaptiveScheduler(new MemoryModel(), [goal]).record(item, NOW, Rating.Good);
    assert.ok(fitted.due < goal.date, 'the review now lands before the quiz');
    assert.ok(daysBetween(fitted.due, goal.date) <= 2.5, 'and close to it');
  });

  it('gives a fast forgetter shorter intervals than a strong memory', () => {
    const weak = new MemoryModel([0.1, 0.4, 0.8, 4, 6.4133, 0.8334, 3.0194, 0.001, 1.4, 0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542]);
    const strong = new MemoryModel();
    const intervalAfterThreeGoods = (memory: MemoryModel) => {
      const scheduler = new AdaptiveScheduler(memory, []);
      let item: ItemState = { ku: unit('x') };
      let at = NOW;
      for (let i = 0; i < 3; i++) {
        const card = scheduler.record(item, at, Rating.Good);
        item = { ...item, card };
        at = card.due;
      }
      return item.card!.scheduled_days;
    };
    assert.ok(intervalAfterThreeGoods(weak) < intervalAfterThreeGoods(strong));
  });
});
