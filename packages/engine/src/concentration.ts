import { ageBand } from './profiles.ts';
import { DEFAULT_TUNING, withTuning, type Tuning } from './tuning.ts';
import type { LearnerProfile } from './types.ts';

/**
 * How a learner concentrates, learned from their own sessions. It drives how
 * long sessions are, how big a chunk to learn by heart, whether to mix
 * subjects, when to ease off, and how long a break should be. Each value
 * starts from an age default and moves toward the learner's data as sessions
 * accumulate (shrinkage), so a few odd days don't swing it.
 */
export interface ConcentrationProfile {
  /** Minutes of good focus before accuracy or speed drops. */
  attentionSpanMinutes: number;
  /** Words per by-heart chunk retained after one study. */
  chunkWords: number;
  /** Accuracy lost right after switching subject (0.1 = 10 points). */
  switchCost: number;
  /** Hours of the day with the best results, e.g. [17, 18]. */
  bestHours: number[];
  /** Break after which results are back to normal. */
  recoveryMinutes: number;
  /** Misses in a row after which the next answer is usually missed too. */
  frustrationAfterMisses: number;
  /** Sessions the estimate is based on (0 = age defaults only). */
  basedOnSessions: number;
}

const DEFAULTS: Record<ReturnType<typeof ageBand>, Omit<ConcentrationProfile, 'basedOnSessions'>> = {
  child: { attentionSpanMinutes: 10, chunkWords: 8, switchCost: 0.1, bestHours: [17], recoveryMinutes: 90, frustrationAfterMisses: 3 },
  'young-teen': { attentionSpanMinutes: 12, chunkWords: 12, switchCost: 0.08, bestHours: [17, 18], recoveryMinutes: 90, frustrationAfterMisses: 3 },
  adult: { attentionSpanMinutes: 20, chunkWords: 20, switchCost: 0.05, bestHours: [20], recoveryMinutes: 60, frustrationAfterMisses: 4 },
};

export function defaultConcentration(age: number): ConcentrationProfile {
  return { ...DEFAULTS[ageBand(age)], basedOnSessions: 0 };
}

export interface LoggedAnswer {
  at: Date;
  correct: boolean;
  latencyMs: number;
  subject: string;
  /** For by-heart chunks answered the first time: the chunk's size in words. */
  chunkWords?: number;
}

export interface SessionLog {
  startedAt: Date;
  answers: LoggedAnswer[];
}

const median = (xs: number[]) => {
  if (!xs.length) return NaN;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
};
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);
const minutes = (a: Date, b: Date) => (b.getTime() - a.getTime()) / 60_000;

/** Pull an observed value toward the prior; `n` observations against a prior worth `k`. */
const shrink = (observed: number, n: number, prior: number, k: number) => (Number.isFinite(observed) && n > 0 ? (n * observed + k * prior) / (n + k) : prior);

export function estimateConcentration(
  logs: readonly SessionLog[],
  prior: ConcentrationProfile,
  t: Tuning['concentration'] = DEFAULT_TUNING.concentration,
): ConcentrationProfile {
  const k = t.priorWeight;
  const sessions = logs.filter((s) => s.answers.length >= 6);

  // Attention span: pooled over sessions, the first minute where accuracy stays well below the start
  // (two minutes running) or answer time rises well above it.
  const buckets = new Map<number, { correct: number[]; latency: number[] }>();
  for (const s of sessions) {
    for (const a of s.answers) {
      const m = Math.floor(minutes(s.startedAt, a.at));
      const b = buckets.get(m) ?? { correct: [], latency: [] };
      b.correct.push(a.correct ? 1 : 0);
      b.latency.push(a.latencyMs);
      buckets.set(m, b);
    }
  }
  const early = [0, 1, 2].flatMap((m) => buckets.get(m)?.correct ?? []);
  const earlyLatency = median([0, 1, 2].flatMap((m) => buckets.get(m)?.latency ?? []));
  const lastMinute = Math.max(-1, ...buckets.keys());
  let span = NaN;
  if (early.length >= 10) {
    const accEarly = mean(early);
    const low = (m: number) => {
      const b = buckets.get(m);
      return b !== undefined && b.correct.length >= 3 && accEarly - mean(b.correct) >= t.attentionDropPoints;
    };
    span = lastMinute + 1; // censored: no drop seen
    for (let m = 3; m <= lastMinute; m++) {
      const slower = median(buckets.get(m)?.latency ?? []) >= earlyLatency * (1 + t.latencyRise);
      if ((low(m) && (low(m + 1) || m === lastMinute)) || slower) {
        span = m;
        break;
      }
    }
  }

  // Chunk size: largest chunk size whose first study usually holds.
  const firstTries = sessions.flatMap((s) => s.answers.filter((a) => a.chunkWords !== undefined));
  const sizes = [...new Set(firstTries.map((a) => a.chunkWords!))].sort((a, b) => a - b);
  let chunk = NaN;
  for (const size of sizes) {
    const tries = firstTries.filter((a) => a.chunkWords === size);
    if (tries.length >= 3 && mean(tries.map((a) => (a.correct ? 1 : 0))) >= t.chunkSuccessTarget) chunk = size;
  }

  // Switch cost: accuracy right after changing subject versus staying on it.
  const after: number[] = [];
  const same: number[] = [];
  for (const s of sessions) {
    s.answers.slice(1).forEach((a, i) => (a.subject === s.answers[i]!.subject ? same : after).push(a.correct ? 1 : 0));
  }
  const switchCost = after.length >= 10 && same.length >= 10 ? Math.max(0, mean(same) - mean(after)) : NaN;

  // Best hours: hours with at least 10 answers and the highest accuracy.
  const byHour = new Map<number, number[]>();
  for (const a of sessions.flatMap((s) => s.answers)) {
    const list = byHour.get(a.at.getHours()) ?? [];
    list.push(a.correct ? 1 : 0);
    byHour.set(a.at.getHours(), list);
  }
  const ranked = [...byHour].filter(([, v]) => v.length >= 10).sort((a, b) => mean(b[1]) - mean(a[1]));
  const bestHours = ranked.length ? ranked.slice(0, 2).map(([h]) => h).sort((a, b) => a - b) : prior.bestHours;

  // Recovery: shortest break after which a session starts as well as the learner does on average.
  const overall = mean(sessions.flatMap((s) => s.answers.map((a) => (a.correct ? 1 : 0))));
  const ordered = [...sessions].sort((a, b) => a.startedAt.getTime() - b.startedAt.getTime());
  const byGap = new Map<number, number[]>();
  ordered.slice(1).forEach((s, i) => {
    const gap = minutes(ordered[i]!.answers.at(-1)!.at, s.startedAt);
    if (gap > 12 * 60) return; // only breaks within a day
    const bucket = [30, 60, 90, 120, 180, 240].find((b) => gap <= b) ?? 240;
    const list = byGap.get(bucket) ?? [];
    list.push(...s.answers.slice(0, 3).map((a) => (a.correct ? 1 : 0)));
    byGap.set(bucket, list);
  });
  const recovered = [...byGap].filter(([, v]) => v.length >= 6 && mean(v) >= overall * 0.95).map(([b]) => b);
  const recovery = recovered.length ? Math.min(...recovered) : NaN;

  // Frustration: smallest run of misses after which the next answer is usually a miss.
  let frustration = NaN;
  for (let run = 2; run <= 6 && Number.isNaN(frustration); run++) {
    const next: number[] = [];
    for (const s of sessions) {
      for (let i = run; i < s.answers.length; i++) {
        if (s.answers.slice(i - run, i).every((a) => !a.correct)) next.push(s.answers[i]!.correct ? 0 : 1);
      }
    }
    if (next.length >= 5 && mean(next) >= 0.6) frustration = run;
  }

  const n = sessions.length;
  return {
    attentionSpanMinutes: Math.round(shrink(span, Number.isNaN(span) ? 0 : sessions.length, prior.attentionSpanMinutes, k)),
    chunkWords: Math.round(shrink(chunk, firstTries.length ? Math.min(n, firstTries.length / 3) : 0, prior.chunkWords, k)),
    switchCost: Math.round(shrink(switchCost, Number.isNaN(switchCost) ? 0 : n, prior.switchCost, k) * 100) / 100,
    bestHours,
    recoveryMinutes: Math.round(shrink(recovery, Number.isNaN(recovery) ? 0 : byGap.size, prior.recoveryMinutes, k)),
    frustrationAfterMisses: Math.round(shrink(frustration, Number.isNaN(frustration) ? 0 : n, prior.frustrationAfterMisses, k)),
    basedOnSessions: n,
  };
}

/**
 * Apply a profile within the family's limits: sessions no longer than the
 * attention span, breaks at least as long as recovery, ease-off at the
 * learner's frustration point, and mixed reviews grouped by subject when
 * switching costs this learner too much.
 */
export function applyConcentration(
  profile: ConcentrationProfile,
  learner: LearnerProfile,
  tuning: Tuning = DEFAULT_TUNING,
): { learner: LearnerProfile; tuning: Tuning; interleaveMixed: boolean; chunkWords: number } {
  return {
    learner: {
      ...learner,
      sessionMinutes: Math.max(5, Math.min(learner.sessionMinutes, profile.attentionSpanMinutes)),
      minGapMinutes: Math.max(learner.minGapMinutes, profile.recoveryMinutes),
    },
    tuning: withTuning(
      { session: { easeOffAfterMisses: profile.frustrationAfterMisses, stopAfterMisses: profile.frustrationAfterMisses + 2 } },
      tuning,
    ),
    interleaveMixed: profile.switchCost <= tuning.concentration.groupAboveSwitchCost,
    chunkWords: profile.chunkWords,
  };
}
