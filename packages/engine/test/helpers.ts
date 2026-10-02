import { Rating, type Grade } from 'ts-fsrs';
import { AdaptiveScheduler, MemoryModel, addDays, type Goal, type ItemState, type KnowledgeUnit, type LearnerProfile } from '../src/index.ts';

export const NOW = new Date('2026-10-02T17:00:00');

export function unit(id: string, overrides: Partial<KnowledgeUnit> = {}): KnowledgeUnit {
  return {
    id,
    subject: 'Maths',
    kind: 'fact',
    title: id,
    importance: 2,
    prerequisites: [],
    goalIds: [],
    cumulative: true,
    ...overrides,
  };
}

export function learner(overrides: Partial<LearnerProfile> = {}): LearnerProfile {
  return {
    id: 'lea',
    name: 'Léa',
    sessionMinutes: 10,
    sessionsPerDay: 1,
    minGapMinutes: 90,
    maxNewPerDay: 6,
    secondsPerProbe: { recognize: 8, recall: 12, apply: 20, explain: 35 },
    latencyMs: { p25: 3000, p75: 9000 },
    recentAccuracy: 0.88,
    ...overrides,
  };
}

/** Study a unit with the given grades, one per `gapDays`, ending `endDaysAgo` days before NOW. */
export function studied(
  ku: KnowledgeUnit,
  grades: Grade[] = [Rating.Good],
  gapDays = 3,
  endDaysAgo = 0,
  goals: Goal[] = [],
): ItemState {
  const scheduler = new AdaptiveScheduler(new MemoryModel(), goals);
  let item: ItemState = { ku };
  const start = addDays(NOW, -endDaysAgo - gapDays * (grades.length - 1));
  grades.forEach((grade, i) => {
    item = { ku, card: scheduler.record(item, addDays(start, i * gapDays), grade) };
  });
  return item;
}
