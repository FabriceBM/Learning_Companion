/**
 * Try the extraction on your own photos:
 *
 *   npm run extract -w @lc/ingest -- "6e" lesson-p1.jpg lesson-p2.jpg
 *
 * Credentials come from the environment (ANTHROPIC_API_KEY or an `ant auth login` profile).
 */
import Anthropic from '@anthropic-ai/sdk';
import { readFile } from 'node:fs/promises';
import { extname } from 'node:path';
import { extractLesson, type Photo } from './extract.ts';

const [level, ...paths] = process.argv.slice(2);
if (!level || paths.length === 0) {
  console.error('Usage: npm run extract -w @lc/ingest -- <level> <photo> [photo...]');
  process.exit(1);
}

const types: Record<string, Photo['mediaType']> = { '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp' };
const photos: Photo[] = await Promise.all(
  paths.map(async (p) => {
    const mediaType = types[extname(p).toLowerCase()];
    if (!mediaType) throw new Error(`${p}: use a .jpg, .png or .webp photo`);
    return { data: await readFile(p), mediaType };
  }),
);

const lesson = await extractLesson(new Anthropic(), photos, { level });
console.log(JSON.stringify(lesson, null, 2));
