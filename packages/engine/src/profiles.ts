/**
 * The app is for children aged 10 to 13 (CM2 to 4e) and their parents, who
 * learn too. Defaults and hard limits follow the age band: a family can choose
 * anything inside the band's limits, never outside them.
 */

export type AgeBand = 'child' | 'young-teen' | 'adult';

export type AnswerMode = 'choices' | 'voice' | 'short-text' | 'maths' | 'free-text';

/** Who sees a learner's progress. */
export type ProgressVisibility =
  | 'family' // children: parents see progress, and the child sees exactly what parents see
  | 'learner-only'; // parents' own learning: nobody else sees it unless they share it

export interface BandDefaults {
  band: AgeBand;
  /** In the French system */
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
    stage: 'CM2–6e, cycle 3 (10–11)',
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
    stage: '5e–4e, cycle 4 (12–13)',
    dailyBudgetMinutes: 15,
    budgetRange: [5, 20],
    maxNewPerDay: 8,
    maxRemindersPerDay: 1,
    // free text means a sentence or two for "explain" questions
    answerModes: ['choices', 'voice', 'short-text', 'maths', 'free-text'],
    visibility: 'family',
    parentalConsent: true,
  },
  adult: {
    band: 'adult',
    stage: 'parents, their own topics',
    dailyBudgetMinutes: 20,
    budgetRange: [5, 45],
    maxNewPerDay: 15,
    maxRemindersPerDay: 2,
    answerModes: ['choices', 'voice', 'short-text', 'maths', 'free-text'],
    visibility: 'learner-only',
    parentalConsent: false,
  },
};

/**
 * Children outside 10–13 fall back to the nearest child band; the stricter
 * child limits also apply to any minor until teen rules are designed.
 */
export function ageBand(age: number): AgeBand {
  if (age < 12) return 'child';
  if (age < 18) return 'young-teen';
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
