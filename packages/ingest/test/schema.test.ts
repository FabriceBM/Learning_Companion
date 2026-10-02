import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { describe, it } from 'node:test';
import { toKnowledgeUnits } from '../src/extract.ts';
import { LessonSchema } from '../src/schema.ts';

const fixture = JSON.parse(await readFile(new URL('../fixtures/fractions-5e.json', import.meta.url), 'utf8'));

describe('lesson schema', () => {
  it('accepts the example lesson', () => {
    assert.equal(LessonSchema.safeParse(fixture).success, true);
  });

  it('maps a lesson onto engine units with namespaced prerequisites', () => {
    const units = toKnowledgeUnits(LessonSchema.parse(fixture), 'maths-5e-l7', { goalIds: ['maths-test-1'], cumulative: true });
    const add = units.find((u) => u.id === 'maths-5e-l7/addition-denominateur-multiple')!;
    assert.deepEqual(add.prerequisites, ['maths-5e-l7/fractions-egales', 'maths-5e-l7/addition-meme-denominateur']);
    assert.equal(add.importance, 2);
    assert.deepEqual(add.goalIds, ['maths-test-1']);
  });
});
