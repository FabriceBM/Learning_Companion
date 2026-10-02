import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { applyConcentration, defaultConcentration, estimateConcentration, seededRng, type SessionLog } from '../src/index.ts';
import { learner } from './helpers.ts';

/** Synthetic sessions: accurate for `span` minutes, then sloppy; worse after a subject switch. */
function sessions(span: number, switchPenalty: number): SessionLog[] {
  const rng = seededRng(5);
  return Array.from({ length: 20 }, (_, d) => {
    const startedAt = new Date(2026, 9, 1 + d, 17, 0);
    const subjects = ['Maths', 'Maths', 'Spanish', 'Spanish', 'French'];
    const answers = Array.from({ length: 30 }, (_, i) => {
      const at = new Date(startedAt.getTime() + i * 30_000);
      const minute = i / 2;
      const switched = i > 0 && subjects[i % 5] !== subjects[(i - 1) % 5];
      const p = (minute < span ? 0.92 : 0.6) - (switched ? switchPenalty : 0);
      return { at, correct: rng() < p, latencyMs: minute < span ? 4000 : 7000, subject: subjects[i % 5]! };
    });
    return { startedAt, answers };
  });
}

describe('concentration profile', () => {
  it('starts from age defaults', () => {
    assert.equal(defaultConcentration(10).attentionSpanMinutes, 10);
    assert.equal(defaultConcentration(40).chunkWords, 20);
  });

  it('learns the attention span and switch cost from sessions, pulled toward the default', () => {
    const p = estimateConcentration(sessions(7, 0.3), defaultConcentration(12));
    assert.ok(p.attentionSpanMinutes >= 6 && p.attentionSpanMinutes <= 9, `span ${p.attentionSpanMinutes}`);
    assert.ok(p.switchCost > 0.15, `switch cost ${p.switchCost}`);
    assert.equal(p.basedOnSessions, 20);
  });

  it('shapes sessions within the family limits', () => {
    const p = { ...defaultConcentration(12), attentionSpanMinutes: 8, switchCost: 0.25, recoveryMinutes: 120, frustrationAfterMisses: 2 };
    const applied = applyConcentration(p, learner({ sessionMinutes: 12, minGapMinutes: 90 }));
    assert.equal(applied.learner.sessionMinutes, 8, 'shorter than the family limit when focus fades sooner');
    assert.equal(applied.learner.minGapMinutes, 120);
    assert.equal(applied.tuning.session.easeOffAfterMisses, 2);
    assert.equal(applied.interleaveMixed, false);
    const long = applyConcentration({ ...p, attentionSpanMinutes: 30 }, learner({ sessionMinutes: 12 }));
    assert.equal(long.learner.sessionMinutes, 12, 'never longer than the family limit');
  });
});
