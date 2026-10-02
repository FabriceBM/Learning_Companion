import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { DEFAULT_TUNING, TUNING_SPEC, getParam, withTuning } from '../src/index.ts';

describe('tuning', () => {
  it('documents every parameter, and every default sits inside its range', () => {
    const leaves = Object.entries(DEFAULT_TUNING).flatMap(([group, values]) => Object.keys(values).map((k) => `${group}.${k}`));
    assert.deepEqual(leaves.sort(), TUNING_SPEC.map((s) => s.path).sort());
    for (const spec of TUNING_SPEC) {
      const value = getParam(DEFAULT_TUNING, spec.path);
      assert.ok(value >= spec.min && value <= spec.max, `${spec.path}=${value} outside [${spec.min}, ${spec.max}]`);
    }
  });

  it('merges overrides and clamps them into range', () => {
    const t = withTuning({ retention: { base: 0.99 }, session: { stopAfterMisses: 4 } });
    assert.equal(t.retention.base, 0.97);
    assert.equal(t.session.stopAfterMisses, 4);
    assert.equal(t.retention.test, DEFAULT_TUNING.retention.test);
    assert.equal(DEFAULT_TUNING.retention.base, 0.9, 'defaults are not mutated');
  });

  it('rejects unknown parameters', () => {
    assert.throws(() => withTuning({ retention: { nope: 1 } as never }));
  });
});
