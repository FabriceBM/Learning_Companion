import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { Rating } from 'ts-fsrs';
import { KnowledgeMap, MemoryModel, PlacementCheck, notionStatus, type Notion } from '../src/index.ts';
import { NOW, studied, unit } from './helpers.ts';
import notions from '../maps/maths-core.json' with { type: 'json' };

const map = new KnowledgeMap(notions as Notion[]);

describe('knowledge map', () => {
  it('rejects unknown prerequisites and cycles', () => {
    assert.throws(() => new KnowledgeMap([{ id: 'a', title: 'A', domain: 'x', prerequisites: ['b'] }]));
    assert.throws(
      () =>
        new KnowledgeMap([
          { id: 'a', title: 'A', domain: 'x', prerequisites: ['b'] },
          { id: 'b', title: 'B', domain: 'x', prerequisites: ['a'] },
        ]),
    );
  });

  it('turns a flagged gap into a path: missing prerequisites first', () => {
    const known = new Set(['whole-numbers', 'multiplication-facts', 'order-of-operations', 'fractions-meaning']);
    const path = map.learningPath(['linear-equations'], (id) => known.has(id)).map((n) => n.id);
    assert.equal(path.at(-1), 'linear-equations');
    assert.ok(path.indexOf('negative-numbers') < path.indexOf('linear-equations'));
    assert.ok(path.indexOf('algebraic-expressions') < path.indexOf('linear-equations'));
    assert.ok(!path.includes('whole-numbers'), 'known notions are skipped');
  });

  it('places a learner on a chain in a handful of questions', () => {
    const chain = new KnowledgeMap(
      Array.from({ length: 16 }, (_, i) => ({ id: `n${i}`, title: `N${i}`, domain: 'x', prerequisites: i ? [`n${i - 1}`] : [] })),
    );
    const knowsUpTo = 9; // truth: n0..n9 known, n10..n15 not
    const check = new PlacementCheck(chain, chain.all.map((n) => n.id));
    for (let n = check.next(); n; n = check.next()) check.record(n.id, Number(n.id.slice(1)) <= knowsUpTo);
    const r = check.result();
    assert.ok(r.asked <= 5, `asked ${r.asked}`);
    assert.equal(r.known.length, 10);
    assert.equal(r.unknown.length, 6);
  });

  it('reads a notion status from the memories of its units', () => {
    const memory = new MemoryModel();
    const solid = studied(unit('a'), [Rating.Good, Rating.Good, Rating.Good, Rating.Good], 15, 1);
    const shaky = studied(unit('b'), [Rating.Hard], 1, 12);
    assert.equal(notionStatus([{ ku: unit('x') }], memory, NOW), 'not-started');
    assert.equal(notionStatus([solid], memory, NOW), 'solid');
    assert.equal(notionStatus([solid, shaky], memory, NOW), 'fragile');
  });
});
