import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { ageBand, defaultsForAge, withinLimits } from '../src/index.ts';

describe('age bands', () => {
  it('maps children 10–13 onto two child bands, and parents onto the adult band', () => {
    assert.deepEqual([10, 11, 12, 13, 40].map(ageBand), ['child', 'child', 'young-teen', 'young-teen', 'adult']);
  });

  it('children share one view with their parents; parents keep their own learning private', () => {
    assert.equal(defaultsForAge(10).visibility, 'family');
    assert.equal(defaultsForAge(13).visibility, 'family');
    assert.equal(defaultsForAge(13).parentalConsent, true);
    assert.equal(defaultsForAge(40).visibility, 'learner-only');
  });

  it('allows up to five sessions of up to 15 minutes for a child, and no more', () => {
    const child = withinLimits(11, { sessionMinutes: 30, sessionsPerDay: 8, maxRemindersPerDay: 3, maxNewPerDay: 30 });
    assert.deepEqual(child, { sessionMinutes: 15, sessionsPerDay: 5, maxRemindersPerDay: 1, maxNewPerDay: 10 });
    const parent = withinLimits(40, { sessionMinutes: 25, sessionsPerDay: 3, maxRemindersPerDay: 2, maxNewPerDay: 12 });
    assert.deepEqual(parent, { sessionMinutes: 25, sessionsPerDay: 3, maxRemindersPerDay: 2, maxNewPerDay: 12 });
  });

  it('never allows more than one reminder a day for a child', () => {
    for (let age = 10; age <= 13; age++) assert.equal(defaultsForAge(age).maxRemindersPerDay, 1);
  });
});
