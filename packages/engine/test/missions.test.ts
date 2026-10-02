import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { Rating } from 'ts-fsrs';
import {
  MIXED_REVIEW,
  MemoryModel,
  addDays,
  missionProgress,
  planSession,
  suggestMissions,
  testMission,
  toFocus,
  topicMission,
  withTuning,
  type Goal,
  type ItemState,
} from '../src/index.ts';
import { NOW, learner, studied, unit } from './helpers.ts';

const memory = new MemoryModel();
const test: Goal = { id: 'fractions-test', title: 'Maths test', date: addDays(NOW, 4) };

/** Fractions (two studied, one weak base, two new) plus plenty of due Spanish and History. */
function world(): ItemState[] {
  const base = studied(unit('equivalent', { title: 'Equivalent fractions', importance: 3 }), [Rating.Hard], 1, 9); // forgotten
  return [
    base,
    studied(unit('add-same', { title: 'Add, same denominator', prerequisites: ['equivalent'], goalIds: [test.id] }), [Rating.Good], 1, 2),
    studied(unit('add-multiple', { title: 'Add, multiple denominator', prerequisites: ['equivalent'], goalIds: [test.id] }), [Rating.Good], 1, 3),
    { ku: unit('subtract', { title: 'Subtract fractions', prerequisites: ['add-same'], goalIds: [test.id] }) },
    { ku: unit('compare', { title: 'Compare fractions', prerequisites: ['equivalent'], goalIds: [test.id] }) },
    ...Array.from({ length: 30 }, (_, i) =>
      studied(unit(`other${i}`, { subject: i % 2 ? 'Spanish' : 'History' }), [Rating.Hard, Rating.Hard], 1, 6),
    ),
  ];
}

describe('missions', () => {
  it('a mission session stays on the mission: other reviews wait', () => {
    const items = world();
    const mission = testMission(test, items);
    const plan = planSession({ learner: learner({ sessionMinutes: 10 }), items, goals: [test], now: NOW, memory, focus: toFocus(mission) });
    const scope = new Set([...mission.kuIds, 'equivalent']);
    assert.ok(plan.items.every((i) => scope.has(i.kuId)), plan.items.map((i) => i.kuId).join());
    assert.ok(plan.waiting > 0, 'the other due reviews are counted as waiting');
  });

  it('repairs a weak prerequisite first, then builds on it', () => {
    const items = world();
    const plan = planSession({ learner: learner(), items, goals: [test], now: NOW, memory, focus: toFocus(testMission(test, items)) });
    assert.equal(plan.items[0]!.kuId, 'equivalent');
    assert.equal(plan.items[0]!.kind, 'repair');
  });

  it('fills a mission session with extra practice until the time is used', () => {
    const items = world();
    const plan = planSession({ learner: learner({ sessionMinutes: 10 }), items, goals: [test], now: NOW, memory, focus: toFocus(testMission(test, items)) });
    assert.ok(plan.items.some((i) => i.kind === 'practice'));
  });

  it('can keep a few at-risk reviews alive when focus is below 100%', () => {
    const items = world();
    const plan = planSession({
      learner: learner({ sessionMinutes: 10 }),
      items,
      goals: [test],
      now: NOW,
      memory,
      focus: toFocus(testMission(test, items)),
      tuning: withTuning({ mission: { focusShare: 0.6 } }),
    });
    assert.ok(plan.items.some((i) => i.kuId.startsWith('other')));
  });

  it('learns a notion in one go: a unit can follow its same-notion prerequisite', () => {
    const notion = (id: string, prerequisites: string[] = []) => unit(id, { notionId: 'negatives', prerequisites });
    const items: ItemState[] = [{ ku: notion('neg/1') }, { ku: notion('neg/2', ['neg/1']) }, { ku: notion('neg/3', ['neg/1']) }];
    const mission = topicMission('neg', 'Negative numbers', items, () => true);
    const focused = planSession({ learner: learner(), items, goals: [], now: NOW, memory, focus: toFocus(mission) });
    const mixed = planSession({ learner: learner(), items, goals: [], now: NOW, memory });
    assert.deepEqual(focused.items.map((i) => i.kuId), ['neg/1', 'neg/2', 'neg/3']);
    assert.deepEqual(mixed.items.map((i) => i.kuId), ['neg/1'], 'outside a mission, dependents wait for a later session');
  });

  it('a notion pushed by parents becomes a mission over its learning path', async () => {
    const { KnowledgeMap, pushedMission } = await import('../src/index.ts');
    const french = (await import('../maps/french-core.json', { with: { type: 'json' } })).default;
    const map = new KnowledgeMap(french);
    const path = map.learningPath(['passe-simple'], (id) => id === 'verb-groups' || id === 'present-indicative');
    assert.deepEqual(path.map((n) => n.id), ['passe-simple']);
    const items: ItemState[] = [1, 2, 3].map((k) => ({ ku: unit(`ps/${k}`, { subject: 'French', notionId: 'passe-simple' }) }));
    const mission = pushedMission('passe-simple', 'Passé simple', path.map((n) => n.id), items, 'your parents');
    assert.equal(mission.kuIds.length, 3);
    const ranked = suggestMissions([MIXED_REVIEW, mission], items, memory, NOW);
    assert.match(ranked.find((r) => r.mission.kind === 'pushed')!.reason, /Pushed by your parents/);
  });

  it('a mixed review interleaves everything that is due', () => {
    const items = world();
    const plan = planSession({ learner: learner(), items, goals: [test], now: NOW, memory, focus: toFocus(MIXED_REVIEW) });
    assert.equal(plan.waiting, 0);
    assert.ok(new Set(plan.items.map((i) => i.subject)).size > 1);
  });

  it('suggests the close test first, and tracks progress', () => {
    const items = world();
    const spanish = topicMission('spanish', 'Spanish verbs', items, (i) => i.ku.subject === 'Spanish');
    const ranked = suggestMissions([MIXED_REVIEW, spanish, testMission(test, items)], items, memory, NOW);
    assert.equal(ranked[0]!.mission.kind, 'test');
    assert.match(ranked[0]!.reason, /In 4 days/);
    const p = missionProgress(testMission(test, items), items, memory, NOW);
    assert.equal(p.total, 4);
    assert.equal(p.started, 2);
    assert.equal(p.complete, false);
  });
});
