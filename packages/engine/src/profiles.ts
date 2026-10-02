/**
 * The app is for children aged 10 to 13 and their parents, who learn too.
 * Knowledge is measured on an absolute map (knowledge-map.ts), not by school
 * grade, so bands only set time limits, answer modes and who sees what. A
 * family can choose anything inside a band's limits, never outside them.
 */

export type AgeBand = 'child' | 'young-teen' | 'adult';

export type AnswerMode = 'choices' | 'voice' | 'short-text' | 'maths' | 'free-text';

/** Who sees a learner's progress. */
export type ProgressVisibility =
  | 'family' // children: parents see progress, and the child sees exactly what parents see
  | 'learner-only'; // parents' own learning: nobody else sees it unless they share it

type Range = [min: number, max: number];

export interface BandDefaults {
  band: AgeBand;
  /** One session: short enough to stay sharp. */
  sessionMinutes: number;
  sessionRange: Range;
  /** Sessions allowed per day; each one is still finite. */
  sessionsPerDay: number;
  sessionsPerDayRange: Range;
  /** Minimum break between two sessions: spacing within the day helps memory. */
  minGapMinutes: number;
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
    sessionMinutes: 10,
    sessionRange: [5, 15],
    sessionsPerDay: 2,
    sessionsPerDayRange: [1, 5],
    minGapMinutes: 90,
    maxNewPerDay: 10,
    maxRemindersPerDay: 1,
    answerModes: ['choices', 'voice', 'short-text'],
    visibility: 'family',
    parentalConsent: true,
  },
  'young-teen': {
    band: 'young-teen',
    sessionMinutes: 12,
    sessionRange: [5, 15],
    sessionsPerDay: 2,
    sessionsPerDayRange: [1, 5],
    minGapMinutes: 90,
    maxNewPerDay: 14,
    maxRemindersPerDay: 1,
    // free text means a sentence or two for "explain" questions
    answerModes: ['choices', 'voice', 'short-text', 'maths', 'free-text'],
    visibility: 'family',
    parentalConsent: true,
  },
  adult: {
    band: 'adult',
    sessionMinutes: 15,
    sessionRange: [5, 30],
    sessionsPerDay: 2,
    sessionsPerDayRange: [1, 5],
    minGapMinutes: 60,
    maxNewPerDay: 20,
    maxRemindersPerDay: 2,
    answerModes: ['choices', 'voice', 'short-text', 'maths', 'free-text'],
    visibility: 'learner-only',
    parentalConsent: false,
  },
};

/** Children outside 10–13 fall back to the nearest child band; any minor keeps the child limits. */
export function ageBand(age: number): AgeBand {
  if (age < 12) return 'child';
  if (age < 18) return 'young-teen';
  return 'adult';
}

export function defaultsForAge(age: number): BandDefaults {
  return BANDS[ageBand(age)];
}

export interface DailyLimits {
  sessionMinutes: number;
  sessionsPerDay: number;
  maxRemindersPerDay: number;
  maxNewPerDay: number;
}

/** Keep what a family or learner chose inside the limits of the learner's age band. */
export function withinLimits(age: number, chosen: DailyLimits): DailyLimits {
  const d = defaultsForAge(age);
  const clamp = (v: number, [lo, hi]: Range) => Math.min(hi, Math.max(lo, v));
  return {
    sessionMinutes: clamp(chosen.sessionMinutes, d.sessionRange),
    sessionsPerDay: clamp(chosen.sessionsPerDay, d.sessionsPerDayRange),
    maxRemindersPerDay: clamp(chosen.maxRemindersPerDay, [0, d.maxRemindersPerDay]),
    maxNewPerDay: clamp(chosen.maxNewPerDay, [0, d.maxNewPerDay]),
  };
}
