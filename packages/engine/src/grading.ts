import { Rating, type Card, type Grade } from 'ts-fsrs';
import type { Attempt, KnowledgeKind, LearnerProfile, ProbeLevel } from './types.ts';

/**
 * Turn an observed answer into an FSRS grade.
 *
 * Children are not asked to rate themselves ("Easy" is the fastest way out of a
 * session, so self-ratings drift). The grade comes from correctness, hints and
 * answer time compared with this child's own typical speed.
 */
export function gradeAttempt(attempt: Attempt, learner: Pick<LearnerProfile, 'latencyMs'>): Grade {
  if (!attempt.correct && !attempt.nearMiss) return Rating.Again;
  if (attempt.nearMiss || attempt.hintsUsed > 0) return Rating.Hard;

  const slow = attempt.latencyMs > learner.latencyMs.p75;
  if (slow || attempt.confidence === 'unsure') return Rating.Hard;

  const fluent = attempt.latencyMs < learner.latencyMs.p25 && attempt.confidence === 'sure';
  // Picking the answer among choices is easier than producing it, so it never counts as Easy.
  if (fluent && attempt.level !== 'recognize') return Rating.Easy;
  return Rating.Good;
}

const LADDER_TOP: Record<KnowledgeKind, ProbeLevel> = {
  term: 'apply', // use the word in a sentence
  fact: 'recall',
  rule: 'apply', // apply the rule to a new sentence
  procedure: 'apply', // a fresh generated exercise each time
  concept: 'explain',
  formula: 'apply',
};

const ORDER: ProbeLevel[] = ['recognize', 'recall', 'apply', 'explain'];

/**
 * Choose the question form from memory stability: recognise while the memory
 * is fragile, then produce, then apply to new material, then explain.
 */
export function probeLevelFor(kind: KnowledgeKind, card: Card | undefined): ProbeLevel {
  const stability = card?.stability ?? 0;
  const wanted: ProbeLevel =
    stability < 3 ? 'recognize' : stability < 10 ? 'recall' : stability < 30 ? 'apply' : 'explain';
  const cap = LADDER_TOP[kind];
  return ORDER.indexOf(wanted) <= ORDER.indexOf(cap) ? wanted : cap;
}
