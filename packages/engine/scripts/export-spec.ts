/**
 * One-off: record the TypeScript engine's behaviour as language-neutral JSON
 * cases (inputs -> expected outputs), written to packages/engine/spec/.
 * Run with TZ=Europe/Paris.
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import { Rating, State, type Card, type Grade } from 'ts-fsrs';
import * as E from '/home/user/Learning_Companion/packages/engine/src/index.ts';
import maths from '/home/user/Learning_Companion/packages/engine/maps/maths-core.json' with { type: 'json' };
import french from '/home/user/Learning_Companion/packages/engine/maps/french-core.json' with { type: 'json' };

const OUT = '/home/user/Learning_Companion/packages/engine/spec';
mkdirSync(OUT, { recursive: true });

const snakeKey = (k: string) => k.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
function snake(x: unknown): unknown {
  if (x instanceof Date) return x.toISOString();
  if (x instanceof Set) return [...x].map(snake);
  if (x instanceof Map) return Object.fromEntries([...x].map(([k, v]) => [k, snake(v)]));
  if (Array.isArray(x)) return x.map(snake);
  if (x && typeof x === 'object') return Object.fromEntries(Object.entries(x).filter(([, v]) => v !== undefined).map(([k, v]) => [snakeKey(k), snake(v)]));
  return x;
}
const write = (name: string, data: unknown) => writeFileSync(`${OUT}/${name}.json`, JSON.stringify(snake(data), null, 1) + '\n');

const card = (c: Card | undefined) =>
  c && c.state !== State.New ? { state: c.state, stability: c.stability, difficulty: c.difficulty, due: c.due, lastReview: c.last_review } : null;
const items = (xs: readonly E.ItemState[]) => xs.map((i) => ({ ku: i.ku, card: card(i.card) }));

// ------------------------------------------------------------- shared helpers (from the TS tests)
const NOW = new Date('2026-10-02T17:00:00');
function unit(id: string, o: Partial<E.KnowledgeUnit> = {}): E.KnowledgeUnit {
  return { id, subject: 'Maths', kind: 'fact', title: id, importance: 2, prerequisites: [], goalIds: [], cumulative: true, ...o };
}
function learner(o: Partial<E.LearnerProfile> = {}): E.LearnerProfile {
  return {
    id: 'lea', name: 'Léa', sessionMinutes: 10, sessionsPerDay: 1, minGapMinutes: 90, maxNewPerDay: 6,
    secondsPerProbe: { recognize: 8, recall: 12, apply: 20, explain: 35 }, latencyMs: { p25: 3000, p75: 9000 }, recentAccuracy: 0.88, ...o,
  };
}
function studied(ku: E.KnowledgeUnit, grades: Grade[] = [Rating.Good], gapDays = 3, endDaysAgo = 0, goals: E.Goal[] = []): E.ItemState {
  const scheduler = new E.AdaptiveScheduler(new E.MemoryModel(), goals);
  let item: E.ItemState = { ku };
  const start = E.addDays(NOW, -endDaysAgo - gapDays * (grades.length - 1));
  grades.forEach((grade, i) => (item = { ku, card: scheduler.record(item, E.addDays(start, i * gapDays), grade) }));
  return item;
}
const stub = (stability: number) => ({ stability }) as Card;

// ------------------------------------------------------------- rng
{
  const seq = (seed: number, n = 8) => { const r = E.seededRng(seed); return Array.from({ length: n }, () => r()); };
  const beta = (a: number, b: number, seed: number) => { const r = E.seededRng(seed); return Array.from({ length: 5 }, () => E.sampleBeta(a, b, r)); };
  write('rng', {
    seeded: [1, 2, 7, 42, 123456789, 4294967295].map((seed) => ({ seed, values: seq(seed) })),
    beta: [[1, 1, 3], [2, 5, 4], [13, 1, 7], [1, 13, 9]].map(([a, b, seed]) => ({ a, b, seed, values: beta(a!, b!, seed!) })),
  });
}

// ------------------------------------------------------------- tuning
{
  const defaults = Object.fromEntries(E.TUNING_SPEC.map((s) => [snakeKey(s.path.split('.')[0]!) + '.' + snakeKey(s.path.split('.')[1]!), E.getParam(E.DEFAULT_TUNING, s.path)]));
  const spec = E.TUNING_SPEC.map((s) => ({ path: snakeKey(s.path.split('.')[0]!) + '.' + snakeKey(s.path.split('.')[1]!), min: s.min, max: s.max, step: s.step }));
  const cases: Array<Record<string, Record<string, number>>> = [
    { retention: { base: 0.99 }, session: { stopAfterMisses: 4 } },
    { retention: { base: 0.5, test: 0.99, testWindowDays: 40 } },
    { mission: { focusShare: 0.2 }, byHeart: { passRatio: 1.5, keyWordsFromDays: 3 } },
    { concentration: { priorWeight: 0, groupAboveSwitchCost: 0.3 }, memory: { maximumIntervalDays: 10000 } },
  ];
  write('tuning', {
    defaults,
    spec,
    withTuning: cases.map((overrides) => {
      const t = E.withTuning(overrides);
      return { overrides, expect: Object.fromEntries(Object.keys(defaults).map((p) => [p, null])) , full: E.TUNING_SPEC.map((s) => [s.path, E.getParam(t, s.path)]) };
    }).map((c) => ({ overrides: c.overrides, expect: Object.fromEntries(c.full.map(([p, v]) => [snakeKey((p as string).split('.')[0]!) + '.' + snakeKey((p as string).split('.')[1]!), v])) })),
    unknown: [{ retention: { nope: 1 } }, { nothing: { base: 0.9 } }],
  });
}

// ------------------------------------------------------------- profiles
write('profiles', {
  ageBand: [8, 10, 11, 11.9, 12, 13, 15, 17, 18, 40].map((age) => ({ age, expect: E.ageBand(age) })),
  defaultsForAge: [10, 13, 40].map((age) => ({ age, expect: E.defaultsForAge(age) })),
  withinLimits: [
    [11, { sessionMinutes: 30, sessionsPerDay: 8, maxRemindersPerDay: 3, maxNewPerDay: 30 }],
    [40, { sessionMinutes: 25, sessionsPerDay: 3, maxRemindersPerDay: 2, maxNewPerDay: 12 }],
    [12, { sessionMinutes: 2, sessionsPerDay: 0, maxRemindersPerDay: -1, maxNewPerDay: 5 }],
    [40, { sessionMinutes: 45, sessionsPerDay: 6, maxRemindersPerDay: 5, maxNewPerDay: 25 }],
  ].map(([age, chosen]) => ({ age, chosen, expect: E.withinLimits(age as number, chosen as E.DailyLimits) })),
});

// ------------------------------------------------------------- day
{
  const morning = new Date('2026-10-03T09:00:00');
  const at = (h: number, m = 0) => new Date(new Date(morning).setHours(h, m, 0, 0));
  const rules = { sessionsPerDay: 4, minGapMinutes: 90 };
  const gates: Array<[Date, E.DayRules, E.DaySoFar]> = [
    [at(9), rules, { sessionsDone: 0 }],
    [at(10), rules, { sessionsDone: 1, lastEndedAt: at(9, 10) }],
    [at(11), rules, { sessionsDone: 1, lastEndedAt: at(9, 10) }],
    [at(20), rules, { sessionsDone: 4, lastEndedAt: at(17) }],
    [at(10, 40), rules, { sessionsDone: 1, lastEndedAt: at(9, 10) }],
    [at(23, 30), { sessionsPerDay: 2, minGapMinutes: 60 }, { sessionsDone: 2, lastEndedAt: at(21) }],
  ];
  const memory = new E.MemoryModel(undefined, { sameDayGapMinutes: 90 });
  const scheduler = new E.AdaptiveScheduler(memory, []);
  const missed: E.ItemState = { ku: unit('tener', { subject: 'Spanish' }) };
  missed.card = scheduler.record(missed, at(9), Rating.Again);
  const fresh: E.ItemState = { ku: unit('nuevo') };
  fresh.card = scheduler.record(fresh, at(9), Rating.Good);
  const old = studied(unit('old'), [Rating.Good, Rating.Good], 3, 2);
  const cards = [missed, fresh, old];
  const times = [at(9, 30), at(10, 30), at(10, 31), at(15), at(23, 59), E.addDays(at(9), 1), E.addDays(at(9), 2), E.addDays(at(9), 9)];
  write('day', {
    sessionGate: gates.map(([now, r, today]) => ({ now, rules: r, today, expect: E.sessionGate(now, r, today) })),
    isDue: cards.flatMap((i) => times.map((now) => ({ card: card(i.card), now, expect: E.isDue(i.card!, now) }))),
    nextUsefulTime: times.map((now) => ({ items: items(cards), now, expect: E.nextUsefulTime(cards, now) ?? null })),
  });
}

// ------------------------------------------------------------- grading
{
  const base = { correct: true, latencyMs: 5000, hintsUsed: 0, level: 'recall' as const };
  const attempts: E.Attempt[] = [
    { ...base, correct: false },
    { ...base, hintsUsed: 1 },
    { ...base, correct: false, nearMiss: true },
    { ...base, latencyMs: 12000 },
    { ...base, latencyMs: 2000, confidence: 'sure' },
    { ...base, latencyMs: 2000, confidence: 'sure', level: 'recognize' },
    { ...base, latencyMs: 2000, confidence: 'unsure' },
    { ...base, latencyMs: 2000 },
    base,
    { ...base, latencyMs: 9000 },
    { ...base, latencyMs: 9001 },
    { ...base, latencyMs: 2999, confidence: 'sure', level: 'explain' },
  ];
  const probes = [
    { id: 'chanter-ils', level: 'apply' as const },
    { id: 'finir-nous', level: 'apply' as const },
    { id: 'etre-il', level: 'apply' as const },
    { id: 'ending-er', level: 'recognize' as const },
    { id: 'why-er', level: 'explain' as const },
  ];
  const kinds: E.KnowledgeKind[] = ['term', 'fact', 'rule', 'procedure', 'concept', 'formula', 'verbatim', 'label'];
  const stabilities = [null, 0, 2.9, 3, 9.99, 10, 29, 30, 120];
  write('grading', {
    gradeAttempt: attempts.map((attempt) => ({ attempt, latencyMs: { p25: 3000, p75: 9000 }, expect: E.gradeAttempt(attempt, learner()) })),
    probeLevelFor: kinds.flatMap((kind) => stabilities.map((s) => ({ kind, stability: s, expect: E.probeLevelFor(kind, s === null ? undefined : stub(s)) }))),
    pickProbe: [
      { level: 'apply', lastAskedAt: { 'chanter-ils': 3, 'finir-nous': 1 } },
      { level: 'apply', lastAskedAt: { 'chanter-ils': 3, 'finir-nous': 1, 'etre-il': 5 } },
      { level: 'recall', lastAskedAt: {} },
      { level: 'explain', lastAskedAt: {} },
      { level: 'apply', lastAskedAt: {} },
    ].map(({ level, lastAskedAt }) => ({
      probes,
      level,
      lastAskedAt,
      expect: E.pickProbe(probes, level as E.ProbeLevel, new Map(Object.entries(lastAskedAt)))?.id ?? null,
    })),
  });
}

// ------------------------------------------------------------- retention
{
  const test: E.Goal = { id: 't1', title: 'History test', date: E.addDays(NOW, 4) };
  const late: E.Goal = { id: 't2', title: 'Later test', date: E.addDays(NOW, 20) };
  const units = [
    unit('a', { goalIds: ['t1'] }),
    unit('b', { goalIds: ['t1'], cumulative: false }),
    unit('c', { goalIds: ['t2'], importance: 3 }),
    unit('d', { importance: 1 }),
    unit('e'),
    unit('f', { goalIds: ['t1', 't2'], cumulative: false, importance: 1 }),
  ];
  const nows = [NOW, E.addDays(NOW, 10), E.addDays(NOW, 25), E.addDays(NOW, -5)];
  write('retention', {
    goals: [test, late],
    targetRetention: units.flatMap((ku) => nows.map((now) => ({ ku, now, expect: E.targetRetention(ku, [test, late], now) }))),
    relaxForLoad: [0.8, 1.1, 1.2, 1.5, 1.8, 3].map((overload) => ({ overload, expect: E.relaxForLoad(E.DEFAULT_RETENTION, overload) })),
  });
}

// ------------------------------------------------------------- by heart
{
  const POEM = `Maître Corbeau, sur un arbre perché,
Tenait en son bec un fromage.
Maître Renard, par l'odeur alléché,
Lui tint à peu près ce langage :
« Hé ! bonjour, Monsieur du Corbeau.
Que vous êtes joli ! que vous me semblez beau ! »`;
  const FULL = POEM + `\nSans mentir, si votre ramage\nSe rapporte à votre plumage,\nVous êtes le Phénix des hôtes de ces bois. »`;
  const PROSE = "La photosynthèse est le processus par lequel les plantes vertes, grâce à l'énergie de la lumière, fabriquent leur matière organique à partir d'eau et de dioxyde de carbone; elle rejette du dioxygène. C'est la base de presque toutes les chaînes alimentaires!";
  const DEF = 'A noun names a person, a place, a thing or an idea.\n\nAn adjective describes a noun.';
  const texts = [POEM, FULL, PROSE, DEF, '  \n  ', 'Un seul vers.'];
  const lines = [
    'Tenait en son bec un fromage.',
    "Maître Renard, par l'odeur alléché,",
    '« Hé ! bonjour, Monsieur du Corbeau.',
    "Aujourd'hui, peut-être 12 élèves — ou 3/4 d'entre eux — l’ont lu.",
    'The water cycle: evaporation, condensation and precipitation.',
    POEM,
  ];
  const levels: E.CueLevel[] = ['read', 'first-letters', 'key-words-blank', 'recite'];
  const recitations: Array<[string, string, boolean]> = [
    ['Maître Corbeau, sur un arbre perché', 'maitre corbeau sur un arbre perche', false],
    ['Maître Corbeau, sur un arbre perché', 'Maître Corbeau sur une branche perché', false],
    ['Maître Corbeau, sur un arbre perché', 'maitre corbeau sur un arbre perche', true],
    ['Maître Corbeau, sur un arbre perché', 'Maître Corbeau, sur un arbre perché', true],
    ['Tenait en son bec un fromage.', 'Tenait un fromage en son bec', false],
    ['Tenait en son bec un fromage.', '', false],
    ['', 'anything', false],
    ["Maître Renard, par l'odeur alléché,", 'Maitre Renard par l odeur alleche', false],
    ["Lui tint à peu près ce langage :", 'Lui tint a peu pres ce langage euh ce langage', false],
    [POEM, POEM.replace('joli', 'gentil').replace('fromage', 'formage'), false],
  ];
  const labels = [
    { id: 'evaporation', label: 'évaporation', box: { x: 0.1, y: 0.5, w: 0.2, h: 0.08 } },
    { id: 'condensation', label: 'condensation', box: { x: 0.4, y: 0.1, w: 0.2, h: 0.08 } },
    { id: 'precipitation', label: 'précipitations', box: { x: 0.7, y: 0.3, w: 0.2, h: 0.08 } },
  ];
  write('by_heart', {
    chunkText: texts.flatMap((text) => [4, 8, 12, 16, 20, 40].map((chunkWords) => ({ text, chunkWords, expect: E.chunkText(text, chunkWords) }))),
    cue: lines.flatMap((text) => levels.map((level) => ({ text, level, expect: E.cue(text, level) }))),
    cueFor: [null, 0, 1.99, 2, 4.99, 5, 30].map((s) => ({ stability: s, expect: E.cueFor(s === null ? undefined : stub(s)) })),
    byHeartUnits: [[POEM, 8], [FULL, 12], [FULL, 40], ['Un seul vers.', 8]].map(([text, size]) => ({
      textId: 'corbeau', title: 'Le Corbeau', subject: 'French', text, chunkWords: size, goalIds: ['recitation'], notionId: 'fables',
      expect: E.byHeartUnits('corbeau', 'Le Corbeau', 'French', E.chunkText(text as string, size as number), { goalIds: ['recitation'], notionId: 'fables' }),
    })),
    figureUnits: [{ figureId: 'water-cycle', title: 'Water cycle', subject: 'Science', labels, expect: E.figureUnits('water-cycle', 'Water cycle', 'Science', labels) }],
    compareRecitation: recitations.map(([expected, given, accents]) => ({ expected, given, accents, expect: E.compareRecitation(expected, given, { accents }) })),
    recitationAttempt: [1, 0.96, 0.95, 0.94, 0.85, 0.84, 0].map((ratio) => ({ ratio, latencyMs: 8000, expect: E.recitationAttempt({ ratio, missing: [] }, 8000) })),
  });
}

// ------------------------------------------------------------- knowledge map
{
  const maps = { 'maths-core': new E.KnowledgeMap(maths as E.Notion[]), 'french-core': new E.KnowledgeMap(french as E.Notion[]) };
  const structure = Object.fromEntries(
    Object.entries(maps).map(([name, map]) => [name, map.all.map((n) => ({ id: n.id, ancestors: [...map.ancestors(n.id)].sort(), descendants: [...map.descendants(n.id)].sort(), depth: map.depth(n.id) }))]),
  );
  const paths: Array<[keyof typeof maps, string[], string[]]> = [
    ['maths-core', ['linear-equations'], ['whole-numbers', 'multiplication-facts', 'order-of-operations', 'fractions-meaning']],
    ['maths-core', ['linear-equations'], []],
    ['maths-core', ['linear-equations', 'fractions-multiply'], ['whole-numbers', 'multiplication-facts', 'division']],
    ['french-core', ['passe-simple'], ['verb-groups', 'present-indicative']],
    ['french-core', ['conditionnel-present', 'agreement-avoir'], ['verb-groups']],
    ['french-core', ['homophones-a'], ['homophones-a']],
  ];
  const placements: Array<[keyof typeof maps, string, string[], number]> = [
    ['maths-core', 'linear-equations', ['whole-numbers', 'multiplication-facts', 'division', 'order-of-operations', 'decimals', 'fractions-meaning', 'equivalent-fractions'], 12],
    ['maths-core', 'linear-equations', [], 12],
    ['maths-core', 'linear-equations', ['whole-numbers', 'multiplication-facts', 'division', 'order-of-operations', 'decimals', 'fractions-meaning', 'equivalent-fractions', 'negative-numbers', 'algebraic-expressions', 'fractions-add'], 3],
    ['french-core', 'conditionnel-present', ['verb-groups', 'present-indicative', 'imparfait'], 12],
  ];
  const chain = Array.from({ length: 16 }, (_, i) => ({ id: `n${i}`, title: `N${i}`, domain: 'x', prerequisites: i ? [`n${i - 1}`] : [] }));
  write('knowledge_map', {
    structure,
    learningPath: paths.map(([name, targets, known]) => ({ map: name, targets, known, expect: maps[name].learningPath(targets, (id) => known.includes(id)).map((n) => n.id) })),
    placement: [
      ...placements.map(([name, target, truth, maxQuestions]) => {
        const map = maps[name];
        const scope = [target, ...map.ancestors(target)];
        const check = new E.PlacementCheck(map, scope, maxQuestions);
        const asked: string[] = [];
        for (let n = check.next(); n; n = check.next()) { asked.push(n.id); check.record(n.id, truth.includes(n.id)); }
        return { map: name, notions: null, scope, truthKnown: truth, maxQuestions, expect: { askedIds: asked, ...check.result() } };
      }),
      (() => {
        const map = new E.KnowledgeMap(chain);
        const scope = chain.map((n) => n.id);
        const truth = scope.filter((id) => Number(id.slice(1)) <= 9);
        const check = new E.PlacementCheck(map, scope);
        const asked: string[] = [];
        for (let n = check.next(); n; n = check.next()) { asked.push(n.id); check.record(n.id, truth.includes(n.id)); }
        return { map: null, notions: chain, scope, truthKnown: truth, maxQuestions: 12, expect: { askedIds: asked, ...check.result() } };
      })(),
    ],
    invalid: [
      [{ id: 'a', title: 'A', domain: 'x', prerequisites: ['b'] }],
      [{ id: 'a', title: 'A', domain: 'x', prerequisites: ['b'] }, { id: 'b', title: 'B', domain: 'x', prerequisites: ['a'] }],
      [{ id: 'a', title: 'A', domain: 'x', prerequisites: ['a'] }],
    ],
  });
}

// ------------------------------------------------------------- planner, missions, notion status
{
  const memory = new E.MemoryModel();
  const subjects = ['Maths', 'Spanish', 'History'];
  const backlog = () => Array.from({ length: 60 }, (_, i) => studied(unit(`u${i}`, { subject: subjects[i % 3]! }), [Rating.Hard, Rating.Hard], 1, 6));
  const test: E.Goal = { id: 'fractions-test', title: 'Maths test', date: E.addDays(NOW, 4) };
  const world = () => [
    studied(unit('equivalent', { title: 'Equivalent fractions', importance: 3 }), [Rating.Hard], 1, 9),
    studied(unit('add-same', { title: 'Add, same denominator', prerequisites: ['equivalent'], goalIds: [test.id] }), [Rating.Good], 1, 2),
    studied(unit('add-multiple', { title: 'Add, multiple denominator', prerequisites: ['equivalent'], goalIds: [test.id] }), [Rating.Good], 1, 3),
    { ku: unit('subtract', { title: 'Subtract fractions', prerequisites: ['add-same'], goalIds: [test.id] }) },
    { ku: unit('compare', { title: 'Compare fractions', prerequisites: ['equivalent'], goalIds: [test.id] }) },
    ...Array.from({ length: 30 }, (_, i) => studied(unit(`other${i}`, { subject: i % 2 ? 'Spanish' : 'History' }), [Rating.Hard, Rating.Hard], 1, 6)),
  ];
  const mixedBag = () => [
    ...Array.from({ length: 12 }, (_, i) => studied(unit(`m${i}`, { subject: subjects[i % 3]!, importance: ((i % 3) + 1) as 1 | 2 | 3, kind: (['term', 'rule', 'concept', 'procedure'] as const)[i % 4] }), [Rating.Good, Rating.Good, Rating.Good].slice(0, 1 + (i % 3)), 2 + (i % 4), i % 5)),
    ...Array.from({ length: 8 }, (_, i) => ({ ku: unit(`fresh${i}`, { subject: subjects[i % 3]!, importance: ((i % 3) + 1) as 1 | 2 | 3, goalIds: i % 2 ? [test.id] : [] }) })),
  ];
  const notionUnits = () => [
    { ku: unit('neg/1', { notionId: 'negatives' }) },
    { ku: unit('neg/2', { notionId: 'negatives', prerequisites: ['neg/1'] }) },
    { ku: unit('neg/3', { notionId: 'negatives', prerequisites: ['neg/1'] }) },
    { ku: unit('alg/1', { notionId: 'algebra', prerequisites: ['neg/2'] }) },
  ];
  type Scenario = { name: string; learner: E.LearnerProfile; items: E.ItemState[]; goals: E.Goal[]; now: Date; tuning?: Record<string, Record<string, number>>; newToday?: number; focus?: { missionId: string; kuIds: string[] }; interleaveMixed?: boolean };
  const w = world();
  const testMission = E.testMission(test, w);
  const nb = notionUnits();
  const scenarios: Scenario[] = [
    { name: 'backlog, 5 minutes', learner: learner({ sessionMinutes: 5 }), items: backlog(), goals: [], now: NOW },
    { name: 'backlog, 8 minutes', learner: learner({ sessionMinutes: 8 }), items: backlog(), goals: [], now: NOW },
    { name: 'backlog, grouped by subject', learner: learner({ sessionMinutes: 8 }), items: backlog(), goals: [], now: NOW, interleaveMixed: false },
    { name: 'prerequisite waits', learner: learner(), items: [{ ku: unit('fractions-equivalent') }, { ku: unit('fractions-add', { prerequisites: ['fractions-equivalent'] }) }], goals: [], now: NOW },
    { name: 'struggling: nothing new', learner: learner({ recentAccuracy: 0.6 }), items: Array.from({ length: 5 }, (_, i) => ({ ku: unit(`n${i}`) })), goals: [], now: NOW },
    { name: 'halved new material', learner: learner({ recentAccuracy: 0.75 }), items: Array.from({ length: 8 }, (_, i) => ({ ku: unit(`n${i}`) })), goals: [], now: NOW },
    { name: 'new quota shared across the day', learner: learner({ maxNewPerDay: 6 }), items: Array.from({ length: 10 }, (_, i) => ({ ku: unit(`n${i}`) })), goals: [], now: NOW, newToday: 4 },
    { name: 'test mission', learner: learner({ sessionMinutes: 10 }), items: w, goals: [test], now: NOW, focus: { missionId: testMission.id, kuIds: testMission.kuIds } },
    { name: 'test mission, focus 60%', learner: learner({ sessionMinutes: 10 }), items: w, goals: [test], now: NOW, focus: { missionId: testMission.id, kuIds: testMission.kuIds }, tuning: { mission: { focusShare: 0.6 } } },
    { name: 'world, mixed review', learner: learner(), items: w, goals: [test], now: NOW },
    { name: 'notion in one go, focused', learner: learner(), items: nb, goals: [], now: NOW, focus: { missionId: 'topic:neg', kuIds: nb.map((i) => i.ku.id) } },
    { name: 'notion, mixed', learner: learner(), items: nb, goals: [], now: NOW },
    { name: 'mixed bag', learner: learner({ sessionMinutes: 12, maxNewPerDay: 4 }), items: mixedBag(), goals: [test], now: NOW },
    { name: 'mixed bag, tuned', learner: learner({ sessionMinutes: 12, maxNewPerDay: 4 }), items: mixedBag(), goals: [test], now: NOW, tuning: { planner: { weightFoundational: 3, riskFloor: 0.2, newUnitCost: 1 }, ladder: { recallFromDays: 1, applyFromDays: 3 } } },
    { name: 'mixed bag, three days later', learner: learner({ sessionMinutes: 15, maxNewPerDay: 4 }), items: mixedBag(), goals: [test], now: E.addDays(NOW, 3.4) },
  ];
  write('planner', {
    scenarios: scenarios.map((s) => {
      const plan = E.planSession({
        learner: s.learner, items: s.items, goals: s.goals, now: s.now, memory,
        tuning: s.tuning ? E.withTuning(s.tuning) : undefined, newToday: s.newToday,
        focus: s.focus ? { missionId: s.focus.missionId, kuIds: new Set(s.focus.kuIds) } : undefined, interleaveMixed: s.interleaveMixed,
      });
      return { ...s, items: items(s.items), expect: plan };
    }),
  });

  // Session runner, on the first backlog plan.
  const plan = E.planSession({ learner: learner({ sessionMinutes: 6 }), items: backlog(), goals: [], now: NOW, memory });
  const runs: Array<{ budget: number; seconds: number; answers: boolean[]; stopAfter?: number; rules?: { easeOffAfterMisses: number; stopAfterMisses: number } }> = [
    { budget: 600, seconds: 10, answers: Array(20).fill(false) },
    { budget: 600, seconds: 10, answers: [false, false, false, true, false, true, true, false, false, false, false, false] },
    { budget: 30, seconds: 12, answers: Array(20).fill(true) },
    { budget: 600, seconds: 8, answers: Array(40).fill(true).map((_, i) => i % 3 !== 0) },
    { budget: 600, seconds: 8, answers: Array(40).fill(true), stopAfter: 4 },
    { budget: 600, seconds: 8, answers: Array(40).fill(false), rules: { easeOffAfterMisses: 2, stopAfterMisses: 4 } },
  ];
  write('session', {
    plan,
    runs: runs.map((r) => {
      const runner = new E.SessionRunner(plan, r.budget, r.rules ?? E.DEFAULT_TUNING.session);
      const steps: unknown[] = [];
      let k = 0;
      for (;;) {
        if (r.stopAfter !== undefined && k === r.stopAfter) runner.stop();
        const step = runner.next();
        if (step.type === 'done') { steps.push({ type: 'done', reason: step.reason }); break; }
        steps.push({ type: 'ask', kuId: step.item.kuId, retry: step.retry });
        runner.answer(step.item, { correct: r.answers[k % r.answers.length]!, latencyMs: 5000, hintsUsed: 0, level: 'recall' }, r.seconds, step.retry);
        k++;
      }
      return { ...r, expect: steps };
    }),
  });

  // Missions: progress and suggestions.
  const spanish = E.topicMission('spanish', 'Spanish verbs', w, (i) => i.ku.subject === 'Spanish');
  const french_ = [1, 2, 3].map((k) => ({ ku: unit(`ps/${k}`, { subject: 'French', notionId: 'passe-simple' }) }));
  const pushed = E.pushedMission('passe-simple', 'Passé simple', ['passe-simple'], french_, 'your parents');
  const farTest: E.Goal = { id: 'far', title: 'Far test', date: E.addDays(NOW, 30) };
  const allItems = [...w, ...french_];
  const missionSets: Array<{ missions: E.Mission[]; items: E.ItemState[]; now: Date }> = [
    { missions: [E.MIXED_REVIEW, spanish, testMission], items: w, now: NOW },
    { missions: [E.MIXED_REVIEW, pushed], items: french_, now: NOW },
    { missions: [E.MIXED_REVIEW, spanish, testMission, pushed, E.testMission(farTest, allItems), E.byHeartMission('corbeau', 'Le Corbeau', ['add-same', 'add-multiple'])], items: allItems, now: NOW },
    { missions: [E.MIXED_REVIEW, spanish, testMission, pushed], items: allItems, now: E.addDays(NOW, 2.5) },
  ];
  write('missions', {
    sets: missionSets.map(({ missions, items: xs, now }) => ({
      missions, items: items(xs), now,
      progress: missions.map((m) => E.missionProgress(m, xs, memory, now)),
      expect: E.suggestMissions(missions, xs, memory, now).map((s) => ({ missionId: s.mission.id, score: s.score, reason: s.reason })),
    })),
    notionStatus: (() => {
      const solid = studied(unit('a'), [Rating.Good, Rating.Good, Rating.Good, Rating.Good], 15, 1);
      const shaky = studied(unit('b'), [Rating.Hard], 1, 12);
      const recent = studied(unit('c'), [Rating.Good, Rating.Good], 2, 0);
      const groups = [[{ ku: unit('x') }], [solid], [solid, shaky], [solid, recent], [solid, { ku: unit('y') }], [recent]];
      return groups.map((g) => ({ units: items(g), now: NOW, expect: E.notionStatus(g, memory, NOW) }));
    })(),
  });
}

// ------------------------------------------------------------- nudge
{
  const settings: E.NudgeSettings = {
    windows: [
      { id: 'after-school', label: 'After school', days: [1, 2, 3, 4, 5], start: '17:00', end: '18:30' },
      { id: 'evening', label: 'Before dinner', days: [1, 2, 3, 4, 5], start: '18:30', end: '19:30' },
      { id: 'saturday', label: 'Saturday morning', days: [6], start: '10:00', end: '12:00' },
    ],
    maxPerDay: 1, restDays: [0], intention: 'After my snack',
  };
  const friday = new Date('2026-10-02T16:00:00');
  const fresh: E.NudgeState = { windows: {}, ignoredStreak: 0, days: [] };
  const ctx = { sessionDoneToday: false, remindersSentToday: 0, plan: { minutes: 9, subjects: ['Spanish', 'Maths'] } };
  const days = (n: number, f: (i: number) => Partial<E.DayRecord>): E.DayRecord[] =>
    Array.from({ length: n }, (_, i) => ({ date: `d${i}`, sessionDone: true, selfStarted: false, nudged: true, ...f(i) }));
  let learned = fresh;
  for (let i = 0; i < 12; i++) { learned = E.recordNudgeOutcome(learned, 'evening', true); learned = E.recordNudgeOutcome(learned, 'after-school', false); }
  learned = { ...learned, ignoredStreak: 0 };
  const cases: Array<{ now: Date; settings: E.NudgeSettings; state: E.NudgeState; ctx: typeof ctx; seed: number }> = [
    { now: friday, settings, state: fresh, ctx, seed: 1 },
    { now: friday, settings: { ...settings, intention: undefined }, state: fresh, ctx, seed: 2 },
    { now: friday, settings, state: fresh, ctx: { ...ctx, sessionDoneToday: true }, seed: 1 },
    { now: new Date('2026-10-04T16:00:00'), settings, state: fresh, ctx, seed: 1 },
    { now: friday, settings, state: fresh, ctx: { ...ctx, remindersSentToday: 1 }, seed: 1 },
    { now: friday, settings: { ...settings, maxPerDay: 0 }, state: fresh, ctx, seed: 1 },
    { now: friday, settings, state: fresh, ctx: { ...ctx, plan: { minutes: 0, subjects: [] } }, seed: 1 },
    { now: friday, settings, state: { ...fresh, days: days(10, (i) => ({ selfStarted: i !== 3, nudged: false })) }, ctx, seed: 1 },
    { now: friday, settings, state: { ...fresh, days: days(10, (i) => ({ selfStarted: i % 2 === 0, nudged: false })) }, ctx, seed: 1 },
    { now: friday, settings, state: { ...fresh, ignoredStreak: 3, days: days(3, () => ({ sessionDone: false })) }, ctx, seed: 1 },
    { now: friday, settings, state: { ...fresh, ignoredStreak: 3, days: days(3, (i) => ({ sessionDone: false, nudged: i < 2 })) }, ctx, seed: 1 },
    { now: friday, settings, state: { ...fresh, ignoredStreak: 6 }, ctx, seed: 1 },
    { now: new Date('2026-10-02T19:45:00'), settings, state: fresh, ctx, seed: 1 },
    { now: new Date('2026-10-02T18:40:00'), settings, state: fresh, ctx, seed: 1 },
    { now: new Date('2026-10-03T08:00:00'), settings, state: fresh, ctx, seed: 1 },
    ...[3, 4, 5, 6, 7, 8, 9, 10].map((seed) => ({ now: friday, settings, state: learned, ctx, seed })),
  ];
  write('nudge', {
    decide: cases.map((c) => ({ ...c, expect: E.decideNudge(c.now, c.settings, c.state, { ...c.ctx, rng: E.seededRng(c.seed) }) })),
    learned,
    reminderText: [['After my snack', 9, ['Spanish', 'Maths']], [undefined, 12, ['French']], [undefined, 5, []]].map(([intention, minutes, subjects]) => ({
      intention: intention ?? null, minutes, subjects, expect: E.reminderText(intention as string | undefined, { minutes: minutes as number, subjects: subjects as string[] }),
    })),
  });
}

// ------------------------------------------------------------- concentration
{
  function sessions(span: number, switchPenalty: number, seed = 5, startHour = 17): E.SessionLog[] {
    const rng = E.seededRng(seed);
    return Array.from({ length: 20 }, (_, d) => {
      const startedAt = new Date(2026, 9, 1 + Math.floor(d / 2), d % 2 ? startHour + 2 : startHour, d % 2 ? 30 : 0);
      const subjects = ['Maths', 'Maths', 'Spanish', 'Spanish', 'French'];
      const answers = Array.from({ length: 30 }, (_, i) => {
        const at = new Date(startedAt.getTime() + i * 30_000);
        const minute = i / 2;
        const switched = i > 0 && subjects[i % 5] !== subjects[(i - 1) % 5];
        const p = (minute < span ? 0.92 : 0.6) - (switched ? switchPenalty : 0);
        return { at, correct: rng() < p, latencyMs: minute < span ? 4000 : 7000, subject: subjects[i % 5]!, chunkWords: i < 6 ? [6, 8, 10, 12, 14, 16][i]! : undefined };
      });
      return { startedAt, answers };
    });
  }
  const logsets: Array<[string, E.SessionLog[], number]> = [
    ['span 7, high switch cost', sessions(7, 0.3), 12],
    ['span 12, no switch cost', sessions(12, 0, 9), 10],
    ['span 4, evening', sessions(4, 0.1, 11, 19), 40],
    ['too little data', sessions(7, 0.3).slice(0, 2).map((s) => ({ ...s, answers: s.answers.slice(0, 5) })), 12],
  ];
  const p = { ...E.defaultConcentration(12), attentionSpanMinutes: 8, switchCost: 0.25, recoveryMinutes: 120, frustrationAfterMisses: 2 };
  write('concentration', {
    defaults: [10, 12, 13, 40].map((age) => ({ age, expect: E.defaultConcentration(age) })),
    estimate: logsets.map(([name, logs, age]) => ({ name, logs, prior: E.defaultConcentration(age), expect: E.estimateConcentration(logs, E.defaultConcentration(age)) })),
    apply: [
      [p, learner({ sessionMinutes: 12, minGapMinutes: 90 })],
      [{ ...p, attentionSpanMinutes: 30 }, learner({ sessionMinutes: 12 })],
      [{ ...p, attentionSpanMinutes: 3, frustrationAfterMisses: 9, switchCost: 0.1 }, learner({ sessionMinutes: 12, minGapMinutes: 150 })],
    ].map(([profile, l]) => {
      const a = E.applyConcentration(profile as E.ConcentrationProfile, l as E.LearnerProfile);
      return { profile, learner: l, expect: { sessionMinutes: a.learner.sessionMinutes, minGapMinutes: a.learner.minGapMinutes, easeOffAfterMisses: a.tuning.session.easeOffAfterMisses, stopAfterMisses: a.tuning.session.stopAfterMisses, interleaveMixed: a.interleaveMixed, chunkWords: a.chunkWords } };
    }),
  });
}

console.log('spec written to', OUT);
