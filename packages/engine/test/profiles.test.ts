import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { ageBand, defaultsForAge, withinLimits } from '../src/index.ts';

describe('age bands', () => {
  it('maps ages 10–30 onto school stages', () => {
    assert.deepEqual([10, 12, 13, 14, 15, 17, 18, 30].map(ageBand), [
      'child', 'child', 'young-teen', 'young-teen', 'teen', 'teen', 'adult', 'adult',
    ]);
  });

  it('gives progress to the learner as they grow up', () => {
    assert.equal(defaultsForAge(11).visibility, 'family');
    assert.equal(defaultsForAge(16).visibility, 'learner-chooses');
    assert.equal(defaultsForAge(24).visibility, 'learner-only');
    assert.equal(defaultsForAge(14).parentalConsent, true);
    assert.equal(defaultsForAge(15).parentalConsent, false);
  });

  it('keeps what a family chooses inside the band limits', () => {
    const child = withinLimits(10, { dailyBudgetMinutes: 60, maxRemindersPerDay: 3, maxNewPerDay: 30 });
    assert.deepEqual(child, { dailyBudgetMinutes: 15, maxRemindersPerDay: 1, maxNewPerDay: 6 });
    const adult = withinLimits(25, { dailyBudgetMinutes: 40, maxRemindersPerDay: 2, maxNewPerDay: 12 });
    assert.deepEqual(adult, { dailyBudgetMinutes: 40, maxRemindersPerDay: 2, maxNewPerDay: 12 });
  });

  it('never allows more than one reminder a day for minors', () => {
    for (let age = 10; age < 18; age++) assert.equal(defaultsForAge(age).maxRemindersPerDay, 1);
  });
});
