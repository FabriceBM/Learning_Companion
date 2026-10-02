import type { Card } from 'ts-fsrs';
import { DEFAULT_TUNING, type Tuning } from './tuning.ts';
import type { Attempt, KnowledgeUnit } from './types.ts';

/**
 * Use case 1: a lesson to learn by heart (a poem, a definition, a summary, a
 * map). The text is cut into chunks sized for this learner, each chunk is
 * learned with cues that fade as memory grows, chunks are chained into longer
 * recitations, and everything comes back on the spaced schedule. Maps and
 * diagrams work the same way with their labels blanked.
 *
 * Audio mode (planned, phase 2): a 'listen' step reads each chunk aloud before
 * 'read', and recitation is spoken; compareRecitation() grades the transcript.
 */

/** How much of the text is shown, from all of it to none of it. */
export type CueLevel = 'read' | 'first-letters' | 'key-words-blank' | 'recite';

export interface Chunk {
  index: number;
  text: string;
  words: number;
}

const wordCount = (s: string) => s.split(/\s+/).filter(Boolean).length;

/**
 * Cut a text into chunks of about `chunkWords` words (from the learner's
 * concentration profile). Cuts fall at line ends, so a verse is never split;
 * a single very long line is split at punctuation.
 */
export function chunkText(text: string, chunkWords: number): Chunk[] {
  const lines = text
    .split(/\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .flatMap((line) => (wordCount(line) > chunkWords * 1.5 ? line.split(/(?<=[,;:.!?»])\s+/) : [line]));
  const chunks: Chunk[] = [];
  let current: string[] = [];
  for (const line of lines) {
    current.push(line);
    if (wordCount(current.join(' ')) >= chunkWords) {
      chunks.push({ index: chunks.length, text: current.join('\n'), words: wordCount(current.join(' ')) });
      current = [];
    }
  }
  if (current.length) {
    // A short tail joins the previous chunk rather than standing alone.
    const tail = current.join('\n');
    const last = chunks.at(-1);
    if (last && wordCount(tail) < chunkWords / 2) {
      last.text += `\n${tail}`;
      last.words += wordCount(tail);
    } else chunks.push({ index: chunks.length, text: tail, words: wordCount(tail) });
  }
  return chunks;
}

const STOP_WORDS = new Set(
  'le la les un une des de du d l à au aux en et ou sur dans par pour que qui ne pas se sa son ses il elle on vous nous je tu me te lui y a est the a an of to in on and or is are be it his her'.split(' '),
);

/** Render a chunk at a cue level. Punctuation and line breaks always stay, they carry the rhythm. */
export function cue(text: string, level: CueLevel): string {
  if (level === 'read') return text;
  if (level === 'recite') return text.replace(/[\p{L}\p{N}’'-]+/gu, '').replace(/[^\n]+/g, '…');
  return text.replace(/[\p{L}\p{N}]+(?:[’'-][\p{L}\p{N}]+)*/gu, (word) => {
    if (level === 'first-letters') return word[0] + '_'.repeat(word.length - 1);
    const isKey = word.length >= 4 && !STOP_WORDS.has(word.toLowerCase());
    return isKey ? '_'.repeat(word.length) : word;
  });
}

/** Cues fade as the chunk's memory stabilises (thresholds in tuning.byHeart). */
export function cueFor(card: Card | undefined, t: Tuning['byHeart'] = DEFAULT_TUNING.byHeart): CueLevel {
  const s = card?.stability ?? 0;
  if (!card) return 'read';
  if (s < t.keyWordsFromDays) return 'first-letters';
  if (s < t.reciteFromDays) return 'key-words-blank';
  return 'recite';
}

/**
 * Units for a text: one per chunk, learned in order, plus chained recitations
 * (chunks 1–2, 1–3, … 1–n). The last chain is the whole text.
 */
export function byHeartUnits(
  textId: string,
  title: string,
  subject: string,
  chunks: readonly Chunk[],
  options: { goalIds?: string[]; notionId?: string } = {},
): KnowledgeUnit[] {
  const base = { subject, kind: 'verbatim' as const, importance: 2 as const, goalIds: options.goalIds ?? [], notionId: options.notionId, cumulative: true };
  const units: KnowledgeUnit[] = chunks.map((c) => ({
    ...base,
    id: `${textId}/c${c.index + 1}`,
    title: `${title}: part ${c.index + 1}`,
    prerequisites: c.index ? [`${textId}/c${c.index}`] : [],
  }));
  for (let k = 2; k <= chunks.length; k++) {
    units.push({
      ...base,
      id: `${textId}/chain${k}`,
      title: k === chunks.length ? `${title}: whole text` : `${title}: parts 1–${k}`,
      prerequisites: [`${textId}/c${k}`, ...(k > 2 ? [`${textId}/chain${k - 1}`] : [`${textId}/c1`])],
    });
  }
  return units;
}

/** A label on a map or diagram; the box is in fractions of the image (0–1), adjustable in the review inbox. */
export interface FigureLabel {
  id: string;
  label: string;
  box: { x: number; y: number; w: number; h: number };
}

/** "Blank the map": one unit per hidden label, then the whole figure with every label hidden. */
export function figureUnits(
  figureId: string,
  title: string,
  subject: string,
  labels: readonly FigureLabel[],
  options: { goalIds?: string[]; notionId?: string } = {},
): KnowledgeUnit[] {
  const base = { subject, kind: 'label' as const, importance: 2 as const, goalIds: options.goalIds ?? [], notionId: options.notionId, cumulative: true };
  const units: KnowledgeUnit[] = labels.map((l) => ({ ...base, id: `${figureId}/${l.id}`, title: `${title}: ${l.label}`, prerequisites: [] }));
  units.push({ ...base, id: `${figureId}/all`, title: `${title}: every label`, prerequisites: units.map((u) => u.id) });
  return units;
}

export interface Recitation {
  /** Share of the expected words recited in order (longest common subsequence). */
  ratio: number;
  /** Expected words that were missing or out of place, for feedback. */
  missing: string[];
}

const tokens = (s: string, accents: boolean) =>
  (accents ? s : s.normalize('NFD').replace(/[̀-ͯ]/g, ''))
    .toLowerCase()
    .replace(/[’']/g, ' ')
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean);

/**
 * Compare a recitation (typed, or a speech transcript in audio mode) with the
 * text, word by word and in order. Accents count when spelling is the point.
 */
export function compareRecitation(expected: string, given: string, options = { accents: false }): Recitation {
  const a = tokens(expected, options.accents);
  const b = tokens(given, options.accents);
  const dp = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      dp[i]![j] = a[i] === b[j] ? dp[i + 1]![j + 1]! + 1 : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!);
    }
  }
  const missing: string[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length) {
    if (j < b.length && a[i] === b[j]) {
      i++;
      j++;
    } else if (j < b.length && dp[i]![j + 1]! >= dp[i + 1]![j]!) j++;
    else missing.push(a[i++]!);
  }
  return { ratio: a.length ? dp[0]![0]! / a.length : 1, missing };
}

/** Turn a recitation into an attempt for grading: near-perfect is correct, close is a near miss. */
export function recitationAttempt(
  r: Recitation,
  latencyMs: number,
  t: Tuning['byHeart'] = DEFAULT_TUNING.byHeart,
): Attempt {
  const correct = r.ratio >= t.passRatio;
  return { correct, nearMiss: !correct && r.ratio >= t.nearMissRatio, latencyMs, hintsUsed: 0, level: 'recall' };
}
