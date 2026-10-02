/**
 * Learners range from 10 to 30. Defaults and hard limits follow the age band:
 * a family can choose anything inside the band's limits, never outside them.
 */

export type AgeBand = 'child' | 'young-teen' | 'teen' | 'adult';

export type AnswerMode = 'choices' | 'voice' | 'short-text' | 'maths' | 'free-text';

/** Who sees a learner's progress by default. */
export type ProgressVisibility =
  | 'family' // under 15: parents see progress, and the child sees exactly what parents see
  | 'learner-chooses' // 15–17: the learner decides what parents see
  | 'learner-only'; // 18+: nobody else sees anything unless the learner shares it

export interface BandDefaults {
  band: AgeBand;
  /** e.g. "CM2–5e" in the French system */
  stage: string;
  dailyBudgetMinutes: number;
  budgetRange: [min: number, max: number];
  maxNewPerDay: number;
  maxRemindersPerDay: number;
  answerModes: AnswerMode[];
  visibility: ProgressVisibility;
  /** Parental consent is needed below 15 in France (digital majority). */
  parentalConsent: boolean;
}

const BANDS: Record<AgeBand, BandDefaults> = {
  child: {
    band: 'child',
    stage: 'CM2–5e (10–12)',
    dailyBudgetMinutes: 10,
    budgetRange: [5, 15],
    maxNewPerDay: 6,
    maxRemindersPerDay: 1,
    answerModes: ['choices', 'voice', 'short-text'],
    visibility: 'family',
    parentalConsent: true,
  },
  'young-teen': {
    band: 'young-teen',
    stage: '4e–3e, brevet (13–14)',
    dailyBudgetMinutes: 15,
    budgetRange: [5, 20],
    maxNewPerDay: 8,
    maxRemindersPerDay: 1,
    answerModes: ['choices', 'voice', 'short-text', 'maths'],
    visibility: 'family',
    parentalConsent: true,
  },
  teen: {
    band: 'teen',
    stage: 'lycée, bac (15–17)',
    dailyBudgetMinutes: 15,
    budgetRange: [5, 30],
    maxNewPerDay: 10,
    maxRemindersPerDay: 1,
    answerModes: ['choices', 'voice', 'short-text', 'maths', 'free-text'],
    visibility: 'learner-chooses',
    parentalConsent: false,
  },
  adult: {
    band: 'adult',
    stage: 'higher education, work, own topics (18–30)',
    dailyBudgetMinutes: 20,
    budgetRange: [5, 45],
    maxNewPerDay: 15,
    maxRemindersPerDay: 2,
    answerModes: ['choices', 'voice', 'short-text', 'maths', 'free-text'],
    visibility: 'learner-only',
    parentalConsent: false,
  },
};

export function ageBand(age: number): AgeBand {
  if (age < 13) return 'child';
  if (age < 15) return 'young-teen';
  if (age < 18) return 'teen';
  return 'adult';
}

export function defaultsForAge(age: number): BandDefaults {
  return BANDS[ageBand(age)];
}

/** Keep what a family or learner chose inside the limits of the learner's age band. */
export function withinLimits(
  age: number,
  chosen: { dailyBudgetMinutes: number; maxRemindersPerDay: number; maxNewPerDay: number },
): { dailyBudgetMinutes: number; maxRemindersPerDay: number; maxNewPerDay: number } {
  const d = defaultsForAge(age);
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  return {
    dailyBudgetMinutes: clamp(chosen.dailyBudgetMinutes, d.budgetRange[0], d.budgetRange[1]),
    maxRemindersPerDay: clamp(chosen.maxRemindersPerDay, 0, d.maxRemindersPerDay),
    maxNewPerDay: clamp(chosen.maxNewPerDay, 0, d.maxNewPerDay),
  };
}
