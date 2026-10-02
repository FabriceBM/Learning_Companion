import { z } from 'zod';

/**
 * What one lesson (one or more photos of a notebook or textbook page) becomes.
 * Everything here is reviewed by a person before it reaches the schedule.
 */

export const ProbeSchema = z.object({
  level: z
    .enum(['recognize', 'recall', 'apply', 'explain'])
    .describe('recognize = pick among choices; recall = produce it; apply = use it on new material; explain = say why'),
  prompt: z.string().describe('The question, in the language of the lesson, worded for the child'),
  answer: z.string().describe('Expected answer; for explain, the key points a good answer contains'),
  choices: z.array(z.string()).nullable().describe('Only for recognize: 3 or 4 options including the answer'),
  grading: z
    .enum(['exact', 'accent_sensitive', 'numeric', 'rubric'])
    .describe('accent_sensitive when spelling is the point (dictation, accents, agreement)'),
});

export const UnitSchema = z.object({
  key: z.string().describe('Short slug, unique within the lesson, e.g. "add-same-denominator"'),
  kind: z.enum(['term', 'fact', 'rule', 'procedure', 'concept', 'formula']),
  title: z.string(),
  statement: z.string().describe("The knowledge itself, keeping the teacher's wording where the photo has it"),
  importance: z.enum(['nice_to_know', 'expected', 'foundational']),
  prerequisites: z.array(z.string()).describe('Keys of other units in this lesson that must be known first'),
  probes: z.array(ProbeSchema).describe('At least one recall-level probe; add other levels when they make sense'),
  misconceptions: z.array(z.string()).describe('Common wrong ideas about this unit, used to write wrong choices and checks'),
  source_quote: z.string().describe('The text in the photo this unit comes from, copied as written'),
  uncertain: z.boolean().describe('True when the photo was hard to read here and a person must check it'),
});

export const LessonSchema = z.object({
  subject: z.string(),
  language: z.string().describe('BCP 47 code of the lesson language, e.g. "fr", "es", "en"'),
  title: z.string(),
  summary: z.string().describe('Two or three sentences a parent can read to know what the lesson is about'),
  units: z.array(UnitSchema),
  unreadable_parts: z.array(z.string()).describe('Where the photo could not be read, so the family can retake it'),
});

export type Lesson = z.infer<typeof LessonSchema>;
export type LessonUnit = z.infer<typeof UnitSchema>;
