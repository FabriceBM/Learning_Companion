/**
 * 60 school days, two synthetic learners, three subjects, three tests.
 *
 * Compares the adaptive engine with a fixed ladder (Leitner/Duolingo-style
 * intervals 1-2-4-7-14-30-60 days that ignore who is learning), both with the
 * same 10-minute daily budget and the same new-material limit.
 *
 * The learners are synthetic: each has a hidden "true" FSRS-6 memory that
 * decides whether an answer is right. The numbers show how the mechanics
 * behave; they are not evidence about real children.
 *
 *   npm run simulate
 */
import { FSRSAlgorithm, Rating, clipParameters, default_w, type Card, type Grade } from 'ts-fsrs';
import {
  AdaptiveScheduler,
  MemoryModel,
  addDays,
  daysBetween,
  fitWeights,
  planSession,
  seededRng,
  type Goal,
  type ItemState,
  type KnowledgeUnit,
  type LearnerProfile,
  type ReviewRecord,
  type Rng,
} from '../src/index.ts';

const START = new Date('2026-09-07T17:00:00'); // Monday, after school
const DAYS = 60;
const SECONDS_PER_REVIEW = 12;
const REFIT_DAYS = [14, 28, 42];

// ---------------------------------------------------------------- curriculum

interface Lesson {
  id: string;
  subject: string;
  day: number;
  cumulative: boolean;
}

const SUBJECTS = [
  { subject: 'Maths', offset: 0, cumulative: true },
  { subject: 'French', offset: 1, cumulative: true },
  { subject: 'Spanish', offset: 2, cumulative: true },
  { subject: 'History', offset: 3, cumulative: false },
];

/** One new lesson per subject per week, 12 units each: about 430 units in 60 days. */
const LESSONS: Lesson[] = SUBJECTS.flatMap(({ subject, offset, cumulative }) =>
  Array.from({ length: 9 }, (_, week) => ({ id: `${subject.toLowerCase()}-${week + 1}`, subject, day: week * 7 + offset, cumulative })),
).filter((l) => l.day < DAYS);

const lessonIds = (subject: string, weeks: number[]) => weeks.map((w) => `${subject.toLowerCase()}-${w}`);

const TESTS = [
  { id: 'maths-1', title: 'Maths test 1', day: 17, lessons: lessonIds('Maths', [1, 2, 3]) },
  { id: 'french', title: 'Dictation', day: 24, lessons: lessonIds('French', [1, 2, 3, 4]) },
  { id: 'spanish', title: 'Spanish quiz', day: 31, lessons: lessonIds('Spanish', [1, 2, 3, 4, 5]) },
  { id: 'history', title: 'History test', day: 45, lessons: lessonIds('History', [3, 4, 5, 6, 7]) },
  { id: 'maths-2', title: 'Maths test 2', day: 52, lessons: lessonIds('Maths', [5, 6, 7, 8]) },
];

/** Tests are in the morning, before that day's after-school session. */
const GOALS: Goal[] = TESTS.map((t) => ({ id: t.id, title: t.title, date: atHour(addDays(START, t.day), 9) }));

function buildUnits(rng: Rng): Array<{ ku: KnowledgeUnit; lesson: Lesson }> {
  const units: Array<{ ku: KnowledgeUnit; lesson: Lesson }> = [];
  for (const lesson of LESSONS) {
    const tests = TESTS.filter((t) => t.lessons.includes(lesson.id)).map((t) => t.id);
    const previous = LESSONS.filter((l) => l.subject === lesson.subject && l.day < lesson.day).at(-1);
    for (let i = 0; i < 12; i++) {
      const r = rng();
      units.push({
        lesson,
        ku: {
          id: `${lesson.id}/${i}`,
          subject: lesson.subject,
          kind: lesson.subject === 'Maths' ? 'procedure' : lesson.subject === 'History' ? 'fact' : lesson.subject === 'French' ? 'rule' : 'term',
          title: `${lesson.id} #${i}`,
          importance: r < 0.2 ? 3 : r < 0.85 ? 2 : 1,
          // In maths, each lesson builds on the first unit of the previous one.
          prerequisites: lesson.subject === 'Maths' && previous ? [`${previous.id}/0`] : [],
          goalIds: tests,
          cumulative: lesson.cumulative,
        },
      });
    }
  }
  // In the order lessons were taught: every policy introduces new material in this order.
  return units.sort((a, b) => a.lesson.day - b.lesson.day);
}

// ---------------------------------------------------------- synthetic minds

interface Mind {
  label: string;
  algorithm: FSRSAlgorithm;
}

/** Hidden truth: scale initial stabilities and shift how fast memories consolidate. */
function mind(label: string, initialScale: number, growthShift: number): Mind {
  const w = [...default_w];
  for (let i = 0; i < 4; i++) w[i] = w[i]! * initialScale;
  w[8] = w[8]! + growthShift;
  return { label, algorithm: new FSRSAlgorithm({ w: clipParameters(w, 0, false), enable_short_term: false }) };
}

const MINDS = [mind('A: forgets fast', 0.45, -0.45), mind('B: strong memory', 1.6, 0.3)];

interface Truth {
  stability: number;
  difficulty: number;
  last: Date;
}

/** The child answers; the hidden memory decides. */
function answer(m: Mind, truth: Truth | undefined, at: Date, rng: Rng): { grade: Grade; recall: number } {
  if (!truth) {
    // First meeting: the child studies the card, then answers it once.
    const r = rng();
    return { grade: r < 0.75 ? Rating.Good : r < 0.92 ? Rating.Hard : Rating.Again, recall: 1 };
  }
  const recall = m.algorithm.forgetting_curve(daysBetween(truth.last, at), truth.stability);
  if (rng() >= recall) return { grade: Rating.Again, recall };
  if (recall > 0.95 && rng() < 0.4) return { grade: Rating.Easy, recall };
  return { grade: recall < 0.75 ? Rating.Hard : Rating.Good, recall };
}

function learnTruth(m: Mind, truth: Truth | undefined, at: Date, grade: Grade): Truth {
  const t = truth ? Math.max(0, Math.round(daysBetween(truth.last, at))) : 0;
  const next = m.algorithm.next_state(truth ? { stability: truth.stability, difficulty: truth.difficulty } : null, t, grade);
  return { ...next, last: at };
}

function trueRecall(m: Mind, truth: Truth | undefined, at: Date): number {
  return truth ? m.algorithm.forgetting_curve(daysBetween(truth.last, at), truth.stability) : 0;
}

// ---------------------------------------------------------------- policies

interface Policy {
  name: string;
  /** Pick today's units within the budget; returns unit ids in order. */
  plan(now: Date, available: KnowledgeUnit[]): string[];
  record(ku: KnowledgeUnit, at: Date, grade: Grade): void;
  /** Called once a day after the session. */
  endOfDay(day: number): Promise<void>;
  /** Predicted recall from this learner's model and from population defaults. */
  predict?(ku: KnowledgeUnit, at: Date): { personal: number; population: number };
  meanInterval?(): number;
}

const PROFILE: LearnerProfile = {
  id: 'sim',
  name: 'sim',
  sessionMinutes: 10,
  sessionsPerDay: 1,
  minGapMinutes: 90,
  maxNewPerDay: 8,
  secondsPerProbe: { recognize: SECONDS_PER_REVIEW, recall: SECONDS_PER_REVIEW, apply: SECONDS_PER_REVIEW, explain: SECONDS_PER_REVIEW },
  latencyMs: { p25: 3000, p75: 9000 },
  recentAccuracy: 0.85,
};

/** FSRS planner and scheduler; optionally refits weights to the child and plans around tests. */
function engine(name: string, options: { personalise: boolean; testAware: boolean }): Policy {
  const goals = options.testAware ? GOALS : [];
  const cards = new Map<string, Card>();
  const population = new Map<string, Card>();
  const populationScheduler = new AdaptiveScheduler(new MemoryModel(), goals);
  const log: ReviewRecord[] = [];
  const recent: boolean[] = [];
  const intervals: number[] = [];
  const units = new Map<string, KnowledgeUnit>();
  let memory = new MemoryModel();
  let scheduler = new AdaptiveScheduler(memory, goals);

  return {
    name,
    plan(now, available) {
      for (const ku of available) units.set(ku.id, ku);
      const items: ItemState[] = available.map((ku) => ({ ku, card: cards.get(ku.id) }));
      const accuracy = recent.length ? recent.filter(Boolean).length / recent.length : 0.85;
      const plan = planSession({ learner: { ...PROFILE, recentAccuracy: accuracy }, items, goals, now, memory });
      return plan.items.map((i) => i.kuId);
    },
    record(ku, at, grade) {
      const card = scheduler.record({ ku, card: cards.get(ku.id) }, at, grade);
      cards.set(ku.id, card);
      population.set(ku.id, populationScheduler.record({ ku, card: population.get(ku.id) }, at, grade));
      log.push({ kuId: ku.id, at, grade });
      recent.push(grade !== Rating.Again);
      if (recent.length > 50) recent.shift();
      if (card.reps >= 3) intervals.push(card.scheduled_days);
    },
    async endOfDay(day) {
      if (!options.personalise || !REFIT_DAYS.includes(day)) return;
      const weights = await fitWeights(log);
      if (!weights) return;
      memory = new MemoryModel(weights);
      scheduler = new AdaptiveScheduler(memory, goals);
      // The review log is the source of truth: replay it to rebuild memory states with the new weights.
      cards.clear();
      for (const r of [...log].sort((a, b) => a.at.getTime() - b.at.getTime())) {
        cards.set(r.kuId, scheduler.record({ ku: units.get(r.kuId)!, card: cards.get(r.kuId) }, r.at, r.grade));
      }
      intervals.length = 0;
    },
    predict: (ku, at) => ({
      personal: memory.retrievability(cards.get(ku.id), at),
      population: populationScheduler.memory.retrievability(population.get(ku.id), at),
    }),
    meanInterval: () => mean(intervals),
  };
}

/** Leitner/Duolingo-style: the same intervals for every child, back to the start on a miss. */
function fixedLadder(): Policy {
  const LADDER = [1, 2, 4, 7, 14, 30, 60];
  const state = new Map<string, { step: number; due: Date }>();
  return {
    name: 'Fixed ladder',
    plan(now, available) {
      const endOfDay = addDays(atHour(now, 0), 1);
      const due = available
        .filter((ku) => state.has(ku.id) && state.get(ku.id)!.due < endOfDay)
        .sort((a, b) => state.get(a.id)!.due.getTime() - state.get(b.id)!.due.getTime());
      const budget = PROFILE.sessionMinutes * 60;
      const picked = due.slice(0, Math.floor(budget / SECONDS_PER_REVIEW)).map((ku) => ku.id);
      let used = picked.length * SECONDS_PER_REVIEW;
      if (picked.length === due.length) {
        for (const ku of available.filter((k) => !state.has(k.id)).slice(0, PROFILE.maxNewPerDay)) {
          if (used + 2 * SECONDS_PER_REVIEW > budget) break;
          picked.push(ku.id);
          used += 2 * SECONDS_PER_REVIEW;
        }
      }
      return picked;
    },
    record(ku, at, grade) {
      const s = state.get(ku.id);
      const step = !s ? 0 : grade === Rating.Again ? 0 : Math.min(s.step + 1, LADDER.length - 1);
      state.set(ku.id, { step, due: addDays(at, LADDER[step]!) });
    },
    async endOfDay() {},
  };
}

// ---------------------------------------------------------------- run

interface Outcome {
  policy: string;
  learner: string;
  minutesPerDay: number;
  tests: number[];
  retainedAtEnd: number;
  learned: number;
  logLoss?: { personal: number; population: number };
  meanInterval?: number;
}

async function run(policy: Policy, m: Mind, seed: number): Promise<Outcome> {
  const units = buildUnits(seededRng(seed));
  const byId = new Map(units.map((u) => [u.ku.id, u.ku]));
  const truth = new Map<string, Truth>();
  const attendance = seededRng(seed + 1);
  const answers = seededRng(seed + 2);
  const minutes: number[] = [];
  const tests: number[] = [];
  const predictions: Array<{ personal: number; population: number; correct: boolean }> = [];

  for (let day = 0; day < DAYS; day++) {
    const now = addDays(START, day);
    for (const t of TESTS.filter((t) => t.day === day)) {
      const tested = units.filter((u) => t.lessons.includes(u.lesson.id));
      tests.push(mean(tested.map((u) => trueRecall(m, truth.get(u.ku.id), atHour(now, 9)))));
    }

    const skip = now.getDay() === 0 || attendance() < 0.1; // Sunday rest + the odd missed day
    if (!skip) {
      const available = units.filter((u) => u.lesson.day <= day).map((u) => u.ku);
      let seconds = 0;
      for (const id of policy.plan(now, available)) {
        const ku = byId.get(id)!;
        const isNew = !truth.has(id);
        const predicted = policy.predict?.(ku, now);
        const { grade } = answer(m, truth.get(id), now, answers);
        // Held-out check: predictions made before the answer, scored on the last 3 weeks.
        if (!isNew && predicted && day >= DAYS - 17) predictions.push({ ...predicted, correct: grade !== Rating.Again });
        truth.set(id, learnTruth(m, truth.get(id), now, grade));
        policy.record(ku, now, grade);
        seconds += isNew ? 2 * SECONDS_PER_REVIEW : SECONDS_PER_REVIEW;
      }
      minutes.push(seconds / 60);
    }
    await policy.endOfDay(day);
  }

  const end = addDays(START, DAYS);
  return {
    policy: policy.name,
    learner: m.label,
    minutesPerDay: mean(minutes),
    tests,
    // Units never studied count as 0: time not spent on them is a real cost.
    retainedAtEnd: mean(units.map((u) => trueRecall(m, truth.get(u.ku.id), end))),
    learned: units.filter((u) => truth.has(u.ku.id)).length,
    logLoss: predictions.length
      ? {
          personal: logLoss(predictions.map((p) => [p.personal, p.correct])),
          population: logLoss(predictions.map((p) => [p.population, p.correct])),
        }
      : undefined,
    meanInterval: policy.meanInterval?.(),
  };
}

function logLoss(rows: Array<[number, boolean]>): number {
  const clamp = (p: number) => Math.min(0.999, Math.max(0.001, p));
  return mean(rows.map(([p, y]) => -(y ? Math.log(clamp(p)) : Math.log(1 - clamp(p)))));
}

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

function atHour(date: Date, hour: number): Date {
  const d = new Date(date);
  d.setHours(hour, 0, 0, 0);
  return d;
}

const pct = (x: number) => `${Math.round(x * 100)}%`;

const POLICIES = [
  () => fixedLadder(),
  () => engine('FSRS, population weights', { personalise: false, testAware: false }),
  () => engine('Adaptive (personal + test-aware)', { personalise: true, testAware: true }),
];

const outcomes: Outcome[] = [];
for (const m of MINDS) {
  for (const make of POLICIES) outcomes.push(await run(make(), m, 42));
}

const unitCount = buildUnits(seededRng(42)).length;
console.log(`\n${DAYS} days · ${unitCount} units in ${LESSONS.length} lessons · one ${PROFILE.sessionMinutes}-min session a day · Sunday off, ~10% of days missed\n`);
console.table(
  outcomes.map((o) => ({
    learner: o.learner,
    policy: o.policy,
    'min/day': o.minutesPerDay.toFixed(1),
    'units studied': o.learned,
    'recall on test days': pct(mean(o.tests)),
    'worst test': pct(Math.min(...o.tests)),
    'all units, recall at day 60': pct(o.retainedAtEnd),
  })),
);

console.log('\nPersonalisation (adaptive engine; weights refitted on days 14, 28, 42):');
console.table(
  outcomes
    .filter((o) => o.policy.startsWith('Adaptive'))
    .map((o) => ({
      learner: o.learner,
      'mean interval, mature units': `${o.meanInterval?.toFixed(1)} days`,
      'log loss, population weights': o.logLoss?.population.toFixed(3),
      'log loss, personal weights': o.logLoss?.personal.toFixed(3),
    })),
);
console.log('Log loss of recall predictions on the last 17 days (lower = the model knows this child better).\n');
