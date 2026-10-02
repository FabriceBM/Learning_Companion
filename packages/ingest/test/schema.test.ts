import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { describe, it } from 'node:test';
import { byHeartUnits, chunkText } from '@lc/engine';
import { toKnowledgeUnits } from '../src/extract.ts';
import { LessonSchema } from '../src/schema.ts';

const fixture = JSON.parse(await readFile(new URL('../fixtures/fractions.json', import.meta.url), 'utf8'));

describe('lesson schema', () => {
  it('accepts the example lesson', () => {
    assert.equal(LessonSchema.safeParse(fixture).success, true);
  });

  it('maps a lesson onto engine units with namespaced prerequisites', () => {
    const units = toKnowledgeUnits(LessonSchema.parse(fixture), 'maths-l7', { goalIds: ['maths-test-1'], cumulative: true });
    const add = units.find((u) => u.id === 'maths-l7/addition-denominateur-multiple')!;
    assert.deepEqual(add.prerequisites, ['maths-l7/fractions-egales', 'maths-l7/addition-meme-denominateur']);
    assert.equal(add.importance, 2);
    assert.deepEqual(add.goalIds, ['maths-test-1']);
    assert.equal(add.notionId, 'adding-and-subtracting-fractions');
  });

  it('a lesson to learn by heart keeps its exact text, which the engine chunks', async () => {
    const corbeau = LessonSchema.parse(JSON.parse(await readFile(new URL('../fixtures/corbeau.json', import.meta.url), 'utf8')));
    assert.equal(corbeau.mode, 'by_heart');
    const chunks = chunkText(corbeau.verbatim_text!, 12);
    const units = byHeartUnits('corbeau', corbeau.title, corbeau.subject, chunks);
    assert.equal(chunks.length, 4);
    assert.match(units.at(-1)!.title, /whole text/);
  });
});
