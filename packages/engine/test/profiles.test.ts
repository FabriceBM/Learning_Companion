import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { ageBand, defaultsForAge, withinLimits } from '../src/index.ts';

describe('age bands', () => {
  it('maps children 10–13 onto cycle 3 and cycle 4, and parents onto the adult band', () => {
    assert.deepEqual([10, 11, 12, 13, 40].map(ageBand), ['child', 'child', 'young-teen', 'young-teen', 'adult']);
  });

  it('children share one view with their parents; parents keep their own learning private', () => {
    assert.equal(defaultsForAge(10).visibility, 'family');
    assert.equal(defaultsForAge(13).visibility, 'family');
    assert.equal(defaultsForAge(13).parentalConsent, true);
    assert.equal(defaultsForAge(40).visibility, 'learner-only');
  });

  it('keeps what a family chooses inside the band limits', () => {
    const child = withinLimits(10, { dailyBudgetMinutes: 60, maxRemindersPerDay: 3, maxNewPerDay: 30 });
    assert.deepEqual(child, { dailyBudgetMinutes: 15, maxRemindersPerDay: 1, maxNewPerDay: 6 });
    const parent = withinLimits(40, { dailyBudgetMinutes: 40, maxRemindersPerDay: 2, maxNewPerDay: 12 });
    assert.deepEqual(parent, { dailyBudgetMinutes: 40, maxRemindersPerDay: 2, maxNewPerDay: 12 });
  });

  it('never allows more than one reminder a day for a child', () => {
    for (let age = 10; age <= 13; age++) assert.equal(defaultsForAge(age).maxRemindersPerDay, 1);
  });
});
