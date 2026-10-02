import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { Rating } from 'ts-fsrs';
import {
  AdaptiveScheduler,
  MemoryModel,
  byHeartUnits,
  chunkText,
  compareRecitation,
  cue,
  cueFor,
  figureUnits,
  gradeAttempt,
  recitationAttempt,
} from '../src/index.ts';
import { NOW, learner } from './helpers.ts';

const POEM = `Maître Corbeau, sur un arbre perché,
Tenait en son bec un fromage.
Maître Renard, par l'odeur alléché,
Lui tint à peu près ce langage :
« Hé ! bonjour, Monsieur du Corbeau.
Que vous êtes joli ! que vous me semblez beau ! »`;

describe('learning by heart', () => {
  it('cuts a text at line ends into chunks of about the learner size', () => {
    const small = chunkText(POEM, 8);
    const large = chunkText(POEM, 16);
    assert.ok(small.length > large.length);
    assert.equal(small[0]!.text, 'Maître Corbeau, sur un arbre perché,\nTenait en son bec un fromage.');
    assert.ok(small.every((c) => !c.text.startsWith(',')), 'never cuts inside a line');
  });

  it('fades the cues: full text, first letters, key words blanked, nothing', () => {
    const line = 'Tenait en son bec un fromage.';
    assert.equal(cue(line, 'read'), line);
    assert.equal(cue(line, 'first-letters'), 'T_____ e_ s__ b__ u_ f______.');
    assert.equal(cue(line, 'key-words-blank'), '______ en son bec un _______.');
    assert.equal(cue(line, 'recite'), '…');
  });

  it('chooses the cue from memory stability', () => {
    const memory = new MemoryModel();
    const scheduler = new AdaptiveScheduler(memory, []);
    const ku = byHeartUnits('corbeau', 'Le Corbeau', 'French', chunkText(POEM, 8))[0]!;
    assert.equal(cueFor(undefined), 'read');
    let card = scheduler.record({ ku }, NOW, Rating.Good);
    assert.equal(cueFor(card), 'key-words-blank');
    card = scheduler.record({ ku, card }, new Date(NOW.getTime() + 3 * 86_400_000), Rating.Good);
    assert.equal(cueFor(card), 'recite');
  });

  it('chains chunks into longer recitations, ending with the whole text', () => {
    const units = byHeartUnits('corbeau', 'Le Corbeau', 'French', chunkText(POEM, 8));
    const ids = units.map((u) => u.id);
    assert.deepEqual(ids, ['corbeau/c1', 'corbeau/c2', 'corbeau/c3', 'corbeau/chain2', 'corbeau/chain3']);
    assert.match(units.at(-1)!.title, /whole text/);
    assert.deepEqual(units.find((u) => u.id === 'corbeau/chain3')!.prerequisites, ['corbeau/c3', 'corbeau/chain2']);
  });

  it('grades a recitation word by word, in order', () => {
    const line = 'Maître Corbeau, sur un arbre perché';
    assert.equal(compareRecitation(line, 'maitre corbeau sur un arbre perche').ratio, 1);
    const slip = compareRecitation(line, 'Maître Corbeau sur une branche perché');
    assert.ok(slip.ratio < 0.95 && slip.ratio > 0.6);
    assert.deepEqual(slip.missing, ['un', 'arbre']);
    assert.ok(compareRecitation(line, 'maitre corbeau sur un arbre perche', { accents: true }).ratio < 1);
    assert.equal(gradeAttempt(recitationAttempt(compareRecitation(line, line), 8000), learner()), Rating.Good);
    assert.equal(gradeAttempt(recitationAttempt(slip, 8000), learner()), Rating.Again);
  });

  it('blanks a map: one unit per label, then the whole map', () => {
    const units = figureUnits('water-cycle', 'Water cycle', 'Science', [
      { id: 'evaporation', label: 'évaporation', box: { x: 0.1, y: 0.5, w: 0.2, h: 0.08 } },
      { id: 'condensation', label: 'condensation', box: { x: 0.4, y: 0.1, w: 0.2, h: 0.08 } },
    ]);
    assert.equal(units.length, 3);
    assert.deepEqual(units.at(-1)!.prerequisites, ['water-cycle/evaporation', 'water-cycle/condensation']);
  });
});
