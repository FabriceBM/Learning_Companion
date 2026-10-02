/**
 * Every fine-tuning knob of the engine, in one place. Defaults come from the
 * learning-science literature or from the simulation; each one can be changed
 * per family (or per learner) within its range. `docs/PARAMETERS.md` is
 * generated from TUNING_SPEC (`npm run params`).
 *
 * Time limits a family sets for each learner (session length, sessions per
 * day, break, reminders, new units per day) live in profiles.ts.
 */

export interface Tuning {
  retention: {
    /** Target probability of recall when a unit comes back. */
    base: number;
    foundational: number;
    niceToKnow: number;
    /** Days before a test during which its units aim higher. */
    testWindowDays: number;
    test: number;
    /** One-off material whose tests are all past. */
    maintenance: number;
  };
  workload: {
    /** Relax everyday targets when needed time / budget stays above this. */
    overloadThreshold: number;
    dropPerOverload: number;
    maxDrop: number;
  };
  ladder: {
    /** Memory stability (days) from which each harder question form is used. */
    recallFromDays: number;
    applyFromDays: number;
    explainFromDays: number;
  };
  planner: {
    weightNiceToKnow: number;
    weightExpected: number;
    weightFoundational: number;
    /** Extra priority for a unit whose test is tomorrow (fades over the test window). */
    testBoost: number;
    /** Added to (target − recall) so units at target still get some priority. */
    riskFloor: number;
    /** A prerequisite counts as known from this predicted recall. */
    prerequisiteRecall: number;
    /** No new material below this recent accuracy... */
    pauseNewBelow: number;
    /** ...and half as much below this one. */
    halveNewBelow: number;
    /** A new unit takes this many times a recognition question (study + answer). */
    newUnitCost: number;
  };
  session: {
    easeOffAfterMisses: number;
    stopAfterMisses: number;
  };
  mission: {
    /** Share of a mission session spent on the mission; the rest goes to the most at-risk other reviews. */
    focusShare: number;
    /** A mission unit is secure once its memory stability reaches this many days. */
    secureStabilityDays: number;
    /** Prerequisites below this recall are repaired first. */
    repairBelowRecall: number;
  };
  reminders: {
    /** Reminders pause once the child starts on their own on this share of active days... */
    selfStartShare: number;
    /** ...over this many days... */
    lookbackDays: number;
    /** ...with at least this many active days. */
    minActiveDays: number;
    backoffAfterIgnored: number;
    stopAfterIgnored: number;
    /** A reminder counts as followed if a session starts within this many minutes. */
    followWindowMinutes: number;
  };
  memory: {
    maximumIntervalDays: number;
    minReviewsToFit: number;
    refitEveryDays: number;
  };
  byHeart: {
    /** Memory stability (days) from which key words are blanked instead of showing first letters... */
    keyWordsFromDays: number;
    /** ...and from which the chunk is recited with nothing shown. */
    reciteFromDays: number;
    /** Share of words recited in order to count as correct... */
    passRatio: number;
    /** ...and as a near miss. */
    nearMissRatio: number;
  };
  concentration: {
    /** How many sessions the age default is worth when blending it with the learner's data. */
    priorWeight: number;
    /** Accuracy drop (points) that marks the end of focus within a session. */
    attentionDropPoints: number;
    /** Rise in answer time that marks the end of focus. */
    latencyRise: number;
    /** A chunk size holds when this share of first studies succeed. */
    chunkSuccessTarget: number;
    /** Above this switch cost, mixed reviews are grouped by subject. */
    groupAboveSwitchCost: number;
  };
}

export const DEFAULT_TUNING: Tuning = {
  retention: { base: 0.9, foundational: 0.92, niceToKnow: 0.85, testWindowDays: 7, test: 0.95, maintenance: 0.8 },
  workload: { overloadThreshold: 1.1, dropPerOverload: 0.05, maxDrop: 0.06 },
  ladder: { recallFromDays: 3, applyFromDays: 10, explainFromDays: 30 },
  planner: {
    weightNiceToKnow: 0.7,
    weightExpected: 1,
    weightFoundational: 1.4,
    testBoost: 1,
    riskFloor: 0.05,
    prerequisiteRecall: 0.8,
    pauseNewBelow: 0.7,
    halveNewBelow: 0.8,
    newUnitCost: 2,
  },
  session: { easeOffAfterMisses: 3, stopAfterMisses: 5 },
  mission: { focusShare: 1, secureStabilityDays: 7, repairBelowRecall: 0.8 },
  reminders: { selfStartShare: 0.8, lookbackDays: 14, minActiveDays: 7, backoffAfterIgnored: 3, stopAfterIgnored: 6, followWindowMinutes: 30 },
  memory: { maximumIntervalDays: 365, minReviewsToFit: 400, refitEveryDays: 7 },
  byHeart: { keyWordsFromDays: 2, reciteFromDays: 5, passRatio: 0.95, nearMissRatio: 0.85 },
  concentration: { priorWeight: 5, attentionDropPoints: 0.15, latencyRise: 0.4, chunkSuccessTarget: 0.7, groupAboveSwitchCost: 0.15 },
};

export interface ParamSpec {
  path: string;
  label: string;
  min: number;
  max: number;
  step: number;
  /** Why the default is what it is. */
  why: string;
}

export const TUNING_SPEC: ParamSpec[] = [
  { path: 'retention.base', label: 'Target recall, everyday units', min: 0.75, max: 0.97, step: 0.01, why: 'Above ~0.9 the review load grows steeply for little gain (FSRS workload curves).' },
  { path: 'retention.foundational', label: 'Target recall, foundational units', min: 0.75, max: 0.97, step: 0.01, why: 'Other units build on these, so forgetting them costs more.' },
  { path: 'retention.niceToKnow', label: 'Target recall, nice-to-know units', min: 0.7, max: 0.95, step: 0.01, why: 'Cheaper upkeep for material that matters less.' },
  { path: 'retention.testWindowDays', label: 'Test window (days)', min: 1, max: 21, step: 1, why: 'A week of higher targets before a test, not more: earlier cramming fades.' },
  { path: 'retention.test', label: 'Target recall before a test', min: 0.85, max: 0.98, step: 0.01, why: 'Aim high only when it is about to be checked.' },
  { path: 'retention.maintenance', label: 'Target recall after a one-off test', min: 0.6, max: 0.9, step: 0.01, why: 'Keeps old chapters alive at little cost.' },
  { path: 'workload.overloadThreshold', label: 'Overload threshold (needed / budget)', min: 1, max: 2, step: 0.05, why: 'Relax targets when the work needed keeps exceeding the time agreed.' },
  { path: 'workload.dropPerOverload', label: 'Target drop per unit of overload', min: 0, max: 0.2, step: 0.01, why: 'Gentle: a 50% overload lowers targets by 0.025.' },
  { path: 'workload.maxDrop', label: 'Largest target drop', min: 0, max: 0.15, step: 0.01, why: 'Never below the maintenance level.' },
  { path: 'ladder.recallFromDays', label: 'Recall questions from (stability, days)', min: 1, max: 14, step: 1, why: 'Pick among choices while a memory is fragile, then produce it.' },
  { path: 'ladder.applyFromDays', label: 'Apply questions from (stability, days)', min: 3, max: 30, step: 1, why: 'Use on new material once recall is reliable (desirable difficulty).' },
  { path: 'ladder.explainFromDays', label: 'Explain questions from (stability, days)', min: 7, max: 90, step: 1, why: 'Explaining why is the deepest check, kept for stable knowledge.' },
  { path: 'planner.weightNiceToKnow', label: 'Priority weight, nice to know', min: 0.1, max: 2, step: 0.1, why: 'Relative priority when time is short.' },
  { path: 'planner.weightExpected', label: 'Priority weight, expected', min: 0.1, max: 2, step: 0.1, why: 'Reference weight.' },
  { path: 'planner.weightFoundational', label: 'Priority weight, foundational', min: 0.1, max: 3, step: 0.1, why: 'Foundations first when time is short.' },
  { path: 'planner.testBoost', label: 'Priority boost the day before a test', min: 0, max: 3, step: 0.1, why: '1 doubles the priority on the eve of the test, fading over the test window.' },
  { path: 'planner.riskFloor', label: 'Priority floor', min: 0, max: 0.2, step: 0.01, why: 'Units right at their target still get some priority.' },
  { path: 'planner.prerequisiteRecall', label: 'Prerequisite counts as known from recall', min: 0.5, max: 0.95, step: 0.05, why: 'New units wait until what they build on is known.' },
  { path: 'planner.pauseNewBelow', label: 'Pause new material below accuracy', min: 0.4, max: 0.9, step: 0.05, why: 'Struggling means consolidate first, not add more.' },
  { path: 'planner.halveNewBelow', label: 'Halve new material below accuracy', min: 0.5, max: 0.95, step: 0.05, why: 'Most answers should succeed: learning is fastest around 85% success.' },
  { path: 'planner.newUnitCost', label: 'Time cost of a new unit (× a question)', min: 1, max: 4, step: 0.5, why: 'Studying the card, then answering it.' },
  { path: 'session.easeOffAfterMisses', label: 'Easier unit after this many misses in a row', min: 2, max: 6, step: 1, why: 'Rebuild confidence before continuing.' },
  { path: 'session.stopAfterMisses', label: 'End the session after this many misses in a row', min: 3, max: 10, step: 1, why: 'Past this point, re-teaching beats more questions.' },
  { path: 'mission.focusShare', label: 'Share of a mission session on the mission', min: 0.5, max: 1, step: 0.05, why: '1 = full focus; lower keeps a few at-risk reviews from other subjects alive.' },
  { path: 'mission.secureStabilityDays', label: 'Mission unit is secure from (stability, days)', min: 3, max: 30, step: 1, why: 'Needs correct answers on separate days (successive relearning), not one good session.' },
  { path: 'mission.repairBelowRecall', label: 'Repair prerequisites below recall', min: 0.5, max: 0.95, step: 0.05, why: 'Fix the foundations before building on them.' },
  { path: 'reminders.selfStartShare', label: 'Pause reminders from this self-start share', min: 0.5, max: 1, step: 0.05, why: 'The habit has formed; the reminder has done its job.' },
  { path: 'reminders.lookbackDays', label: 'Self-start measured over (days)', min: 7, max: 28, step: 1, why: 'Two weeks smooths out holidays and busy days.' },
  { path: 'reminders.minActiveDays', label: 'Minimum active days before pausing', min: 3, max: 14, step: 1, why: 'Do not conclude from too few days.' },
  { path: 'reminders.backoffAfterIgnored', label: 'Every other day after this many ignored', min: 2, max: 10, step: 1, why: 'Back off, never escalate.' },
  { path: 'reminders.stopAfterIgnored', label: 'Stop reminding after this many ignored', min: 3, max: 15, step: 1, why: 'Then parents see it in the weekly summary instead.' },
  { path: 'reminders.followWindowMinutes', label: 'Reminder followed if a session starts within (min)', min: 10, max: 120, step: 5, why: 'Used to learn which time slot works for each child.' },
  { path: 'memory.maximumIntervalDays', label: 'Longest gap between reviews (days)', min: 30, max: 3650, step: 5, why: 'A yearly check even on very stable memories.' },
  { path: 'memory.minReviewsToFit', label: 'Reviews needed before personal fitting', min: 100, max: 2000, step: 50, why: 'Below this, defaults predict better than a fit.' },
  { path: 'memory.refitEveryDays', label: 'Refit personal weights every (days)', min: 1, max: 30, step: 1, why: 'Weekly is enough; memory habits change slowly.' },
  { path: 'byHeart.keyWordsFromDays', label: 'Blank key words from (stability, days)', min: 0.5, max: 7, step: 0.5, why: 'First letters while the text is fresh, then only the small words stay.' },
  { path: 'byHeart.reciteFromDays', label: 'Recite with nothing shown from (stability, days)', min: 1, max: 21, step: 1, why: 'Fading cues: the support disappears as memory takes over.' },
  { path: 'byHeart.passRatio', label: 'Recitation correct from (share of words in order)', min: 0.8, max: 1, step: 0.01, why: 'Word for word means nearly every word, in order.' },
  { path: 'byHeart.nearMissRatio', label: 'Recitation near miss from', min: 0.6, max: 0.98, step: 0.01, why: 'Close enough to come back soon, not from scratch.' },
  { path: 'concentration.priorWeight', label: 'Age default worth (sessions)', min: 1, max: 30, step: 1, why: 'A few odd days must not swing the profile.' },
  { path: 'concentration.attentionDropPoints', label: 'Focus ends at an accuracy drop of', min: 0.05, max: 0.4, step: 0.05, why: '15 points below the session start is a clear dip.' },
  { path: 'concentration.latencyRise', label: 'Focus ends at an answer-time rise of', min: 0.1, max: 1, step: 0.05, why: 'Slowing down by 40% is the other sign of fatigue.' },
  { path: 'concentration.chunkSuccessTarget', label: 'Chunk size holds from first-study success of', min: 0.5, max: 0.95, step: 0.05, why: 'Bigger chunks while 70% stick on first study; smaller below.' },
  { path: 'concentration.groupAboveSwitchCost', label: 'Group mixed reviews by subject above switch cost', min: 0, max: 0.5, step: 0.01, why: 'Interleaving helps most learners; not one who loses 15 points per switch.' },
];

type DeepPartial<T> = { [K in keyof T]?: T[K] extends object ? DeepPartial<T[K]> : T[K] };

export function getParam(tuning: Tuning, path: string): number {
  const [group, key] = path.split('.') as [keyof Tuning, string];
  return (tuning[group] as unknown as Record<string, number>)[key]!;
}

/** Merge overrides onto the defaults, clamping every value into its allowed range. */
export function withTuning(overrides: DeepPartial<Tuning> = {}, base: Tuning = DEFAULT_TUNING): Tuning {
  const merged = structuredClone(base) as unknown as Record<string, Record<string, number>>;
  for (const [group, values] of Object.entries(overrides)) {
    for (const [key, value] of Object.entries(values ?? {})) {
      if (typeof value !== 'number') continue;
      const spec = TUNING_SPEC.find((s) => s.path === `${group}.${key}`);
      if (!spec || !merged[group]) throw new Error(`Unknown parameter ${group}.${key}`);
      merged[group]![key] = Math.min(spec.max, Math.max(spec.min, value));
    }
  }
  return merged as unknown as Tuning;
}
