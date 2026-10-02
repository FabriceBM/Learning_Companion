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

Copy the text each unit comes from into "source_quote". When handwriting or the photo is unclear, say so with "uncertain" and in "unreadable_parts" rather than guessing.`;

/**
 * Photo(s) of one lesson -> structured lesson. Runs on the server (the API key
 * never ships in the app). The result goes to the family's review inbox, not
 * straight into the schedule.
 */
export async function extractLesson(client: Anthropic, photos: Photo[], context: LessonContext): Promise<Lesson> {
  const response = await client.beta.messages.parse({
    model: 'claude-opus-5-5',
    max_tokens: 16000,
    output_config: { effort: 'high', format: betaZodOutputFormat(LessonSchema) },
    // If the model declines (unlikely for school material), the API retries on a fallback model in the same call.
    betas: ['server-side-fallback-2026-07-01'],
    fallbacks: 'default',
    system: SYSTEM,
    messages: [
      {
        role: 'user',
        content: [
          ...photos.map((p) => ({
            type: 'image' as const,
            source: { type: 'base64' as const, media_type: p.mediaType, data: p.data.toString('base64') },
          })),
          {
            type: 'text' as const,
            text: `Level: ${context.level}.${context.subjectHint ? ` Subject: ${context.subjectHint}.` : ''} Extract the lesson.`,
          },
        ],
      },
    ],
  });

  if (response.stop_reason === 'refusal') {
    throw new Error(`Extraction declined: ${response.stop_details?.explanation ?? 'no explanation'}`);
  }
  if (response.stop_reason === 'max_tokens') {
    throw new Error('Lesson too long for one pass: split the photos into smaller groups.');
  }
  if (!response.parsed_output) throw new Error('The model returned output that does not match the lesson schema.');
  return response.parsed_output;
}

const IMPORTANCE = { nice_to_know: 1, expected: 2, foundational: 3 } as const;

/** Map an accepted lesson onto the engine's units. Cumulative subjects keep their retention target after tests. */
export function toKnowledgeUnits(lesson: Lesson, lessonId: string, options: { goalIds?: string[]; cumulative: boolean }): KnowledgeUnit[] {
  const id = (key: string) => `${lessonId}/${key}`;
  return lesson.units.map((u) => ({
    id: id(u.key),
    subject: lesson.subject,
    kind: u.kind,
    title: u.title,
    importance: IMPORTANCE[u.importance],
    prerequisites: u.prerequisites.map(id),
    goalIds: options.goalIds ?? [],
    cumulative: options.cumulative,
  }));
}
