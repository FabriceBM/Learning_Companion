import Anthropic from '@anthropic-ai/sdk';
import { betaZodOutputFormat } from '@anthropic-ai/sdk/helpers/beta/zod';
import type { KnowledgeUnit } from '@lc/engine';
import { LessonSchema, type Lesson } from './schema.ts';

export interface Photo {
  data: Buffer;
  mediaType: 'image/jpeg' | 'image/png' | 'image/webp';
}

export interface LessonContext {
  /** e.g. "6e (France, cycle 3)", "CE2", "adult, Spanish B1" */
  level: string;
  /** If the family already said which subject this is. */
  subjectHint?: string;
}

// Stable across calls so it can be cached; the per-lesson details go in the user turn.
const SYSTEM = `You turn photos of a school lesson (notebook pages, worksheets, textbook pages) into material for spaced retrieval practice for a child.

Split the lesson into small units of knowledge: one word, one rule, one date, one method, one idea per unit. Treat every subject as a language: vocabulary, spelling and grammar rules, dates, formulas and methods are all units.

Keep the teacher's wording in "statement" wherever the photo has it: the child is assessed on the teacher's version. Write questions in the language of the lesson, at the child's level, and never make a question that can be answered without knowing the unit. For maths methods, write questions with fresh numbers rather than the worked example from the page.

Name each unit's "notion" generically, the way it would appear on a map of knowledge independent of any school system or grade.

When the page is meant to be learned by heart (a poem, a definition or rule marked to learn, a text to recite), set "mode" to "by_heart" and copy the text exactly into "verbatim_text", keeping line breaks and punctuation; the app cuts it into chunks itself. When a map or diagram has labels to know, list each label with an approximate box so it can be blanked; a person adjusts the boxes in the review inbox.

Copy the text each unit comes from into "source_quote". When handwriting or the photo is unclear, say so with "uncertain" and in "unreadable_parts" rather than guessing.`;

const TEACH = `You write a short lesson for one notion that a parent found missing in their child's knowledge, as material for spaced retrieval practice. There is no photo: the lesson is yours.

Assume the listed prerequisites are known and build on them; do not re-teach them. Split the notion into small units (one idea or step each), clear enough for the child's age, with a statement, questions at several levels, and the usual misconceptions. This is for practice in free sessions, not word-for-word learning: for every rule or method, write at least eight varied apply-level questions (different verbs and persons for a conjugation, different numbers for a method) so practice never repeats the same item. Name every unit's "notion" with the notion given. Set "mode" to "understand", "verbatim_text" to null and "figure_labels" to empty. Leave "source_quote" empty and "uncertain" false; "unreadable_parts" is empty.`;

/**
 * Photo(s) of one lesson -> structured lesson. Runs on the server (the API key
 * never ships in the app). The result goes to the family's review inbox, not
 * straight into the schedule.
 */
export async function extractLesson(client: Anthropic, photos: Photo[], context: LessonContext): Promise<Lesson> {
  return requestLesson(client, SYSTEM, [
    ...photos.map((p) => ({
      type: 'image' as const,
      source: { type: 'base64' as const, media_type: p.mediaType, data: p.data.toString('base64') },
    })),
    {
      type: 'text' as const,
      text: `Level: ${context.level}.${context.subjectHint ? ` Subject: ${context.subjectHint}.` : ''} Extract the lesson.`,
    },
  ]);
}

export interface NotionRequest {
  /** As the parent wrote it, or as named on the knowledge map. */
  notion: string;
  learnerAge: number;
  /** Notions already known (from the placement check), to build on rather than re-teach. */
  knownPrerequisites: string[];
  /** Language the child learns in, e.g. "fr". */
  language: string;
  /** Optional context from the parent: "starts high school next September". */
  why?: string;
}

/**
 * A gap a parent flagged, with no lesson to photograph: write the lesson.
 * Same output as extractLesson, so it goes through the same review inbox.
 */
export async function teachNotion(client: Anthropic, request: NotionRequest): Promise<Lesson> {
  const lines = [
    `Notion: ${request.notion}`,
    `Child's age: ${request.learnerAge}`,
    `Language: ${request.language}`,
    `Already known: ${request.knownPrerequisites.join('; ') || 'nothing listed'}`,
    request.why ? `Why the parents flagged it: ${request.why}` : '',
  ];
  return requestLesson(client, TEACH, [{ type: 'text' as const, text: lines.filter(Boolean).join('\n') }]);
}

type LessonContent = Parameters<Anthropic['beta']['messages']['parse']>[0]['messages'][number]['content'];

async function requestLesson(client: Anthropic, system: string, content: LessonContent): Promise<Lesson> {
  const response = await client.beta.messages.parse({
    model: 'claude-opus-5-5',
    max_tokens: 16000,
    output_config: { effort: 'high', format: betaZodOutputFormat(LessonSchema) },
    // If the model declines (unlikely for school material), the API retries on a fallback model in the same call.
    betas: ['server-side-fallback-2026-07-01'],
    fallbacks: 'default',
    system,
    messages: [{ role: 'user', content }],
  });

  if (response.stop_reason === 'refusal') {
    throw new Error(`Lesson request declined: ${response.stop_details?.explanation ?? 'no explanation'}`);
  }
  if (response.stop_reason === 'max_tokens') {
    throw new Error('Lesson too long for one pass: split it into smaller parts (fewer photos, or a narrower notion).');
  }
  if (!response.parsed_output) throw new Error('The model returned output that does not match the lesson schema.');
  return response.parsed_output;
}

const IMPORTANCE = { nice_to_know: 1, expected: 2, foundational: 3 } as const;

/** A notion name → its id on the knowledge map. The app resolves names against the existing map first. */
export const notionSlug = (name: string) =>
  name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');

/** Map an accepted lesson onto the engine's units. Cumulative subjects keep their retention target after tests. */
export function toKnowledgeUnits(
  lesson: Lesson,
  lessonId: string,
  options: { goalIds?: string[]; cumulative: boolean; notionId?: (name: string) => string },
): KnowledgeUnit[] {
  const id = (key: string) => `${lessonId}/${key}`;
  return lesson.units.map((u) => ({
    id: id(u.key),
    subject: lesson.subject,
    kind: u.kind,
    title: u.title,
    notionId: (options.notionId ?? notionSlug)(u.notion),
    importance: IMPORTANCE[u.importance],
    prerequisites: u.prerequisites.map(id),
    goalIds: options.goalIds ?? [],
    cumulative: options.cumulative,
  }));
}
