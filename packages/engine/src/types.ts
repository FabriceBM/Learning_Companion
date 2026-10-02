import type { Card } from 'ts-fsrs';

/**
 * Every subject is treated as "a language": a word, a spelling rule, a date,
 * a formula and a method are all units of knowledge with their own memory curve.
 */
export type KnowledgeKind =
  | 'term' // vocabulary, definitions: "photosynthèse", "tener"
  | 'fact' // dates, places, constants
  | 'rule' // grammar, spelling, sign rules (with exceptions)
  | 'procedure' // methods: adding fractions, solving an equation
  | 'concept' // ideas that need explaining: why the seasons change
  | 'formula'
  | 'verbatim' // learned word for word: a poem, a definition (by-heart.ts)
  | 'label'; // a label on a map or diagram, learned by blanking it (by-heart.ts)

/**
 * Question forms, from easiest to hardest. The same unit climbs this ladder as
 * its memory gets more stable (desirable difficulty), so the child is never
 * drilled on the identical flashcard forever.
 */
export type ProbeLevel = 'recognize' | 'recall' | 'apply' | 'explain';

export interface KnowledgeUnit {
  id: string;
  subject: string;
  kind: KnowledgeKind;
  title: string;
  /** 1 = nice to know, 2 = expected, 3 = foundational (other units build on it). */
  importance: 1 | 2 | 3;
  /** Units that should be stable before this one is introduced. */
  prerequisites: string[];
  /** Tests or projects this unit counts for. */
  goalIds: string[];
  /** The notion on the knowledge map this unit belongs to (see knowledge-map.ts). */
  notionId?: string;
  /**
   * Cumulative knowledge (times tables, conjugations) keeps a normal retention
   * target after its tests; one-off material drops to a cheap maintenance level.
   */
  cumulative: boolean;
}

/** A dated assessment: a class test, an oral, an exam. */
export interface Goal {
  id: string;
  title: string;
  date: Date;
}

export interface LearnerProfile {
  id: string;
  name: string;
  /** FSRS-6 weights fitted to this learner's history; undefined means population defaults. */
  weights?: readonly number[];
  /** Length of one session, agreed between child and parent; the planner never exceeds it. */
  sessionMinutes: number;
  /** Most sessions in a day, each at least `minGapMinutes` after the previous one. */
  sessionsPerDay: number;
  minGapMinutes: number;
  /** New units per day, across all of the day's sessions. */
  maxNewPerDay: number;
  /** Typical seconds per question at each level, learned from the learner's history. */
  secondsPerProbe: Record<ProbeLevel, number>;
  /** Answer-time quartiles (ms), used to tell fluent answers from laboured ones. */
  latencyMs: { p25: number; p75: number };
  /** Accuracy over the last ~50 answers; throttles new material when the child is struggling. */
  recentAccuracy: number;
}

/** A unit together with this learner's memory of it. */
export interface ItemState {
  ku: KnowledgeUnit;
  /** Undefined until the unit has been studied once. */
  card?: Card;
}

/** What actually happened when the child answered. Grading is objective, never self-rated. */
export interface Attempt {
  correct: boolean;
  /** Right idea with a small slip (a typo when the unit is not about spelling). */
  nearMiss?: boolean;
  latencyMs: number;
  hintsUsed: number;
  /** Optional "sure / not sure" tap before the answer is revealed (trains calibration). */
  confidence?: 'sure' | 'unsure';
  level: ProbeLevel;
}
