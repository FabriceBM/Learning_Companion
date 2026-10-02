import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { Rating } from 'ts-fsrs';
import { addDays, fitWeights, seededRng, type ReviewRecord } from '../src/index.ts';
import { NOW } from './helpers.ts';

describe('fitWeights', () => {
  it('waits for enough history', async () => {
    assert.equal(await fitWeights([{ kuId: 'a', at: NOW, grade: Rating.Good }]), undefined);
  });

  it('fits 21 FSRS-6 weights from a review log', async () => {
    const rng = seededRng(3);
    const log: ReviewRecord[] = [];
    for (let u = 0; u < 120; u++) {
      let day = 0;
      for (const gap of [0, 1, 3, 7, 15]) {
        day += gap;
        log.push({ kuId: `u${u}`, at: addDays(NOW, day), grade: rng() < 0.15 ? Rating.Again : Rating.Good });
      }
    }
    const weights = await fitWeights(log);
    assert.equal(weights?.length, 21);
    assert.ok(weights!.every(Number.isFinite));
  });
});
