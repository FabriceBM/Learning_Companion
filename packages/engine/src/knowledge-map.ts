import { MemoryModel } from './memory.ts';
import type { ItemState } from './types.ts';

/**
 * Knowledge measured on an absolute map, not by school grade. A notion is one
 * idea or skill ("adding fractions with different denominators"); it lists the
 * notions it builds on. Any curriculum, a parent's judgement ("our eldest
 * lacks this before high school") or a photographed lesson just points at
 * notions on the same map.
 */
export interface Notion {
  id: string;
  title: string;
  /** Domain › area › notion, e.g. French › Conjugation › Passé simple. */
  domain: string;
  area?: string;
  prerequisites: string[];
  /** Optional absolute level label where the domain has one, e.g. CEFR "A2" for languages. */
  level?: string;
}

export class KnowledgeMap {
  private readonly notions = new Map<string, Notion>();

  constructor(notions: readonly Notion[]) {
    for (const n of notions) this.notions.set(n.id, n);
    for (const n of notions) {
      for (const p of n.prerequisites) if (!this.notions.has(p)) throw new Error(`${n.id}: unknown prerequisite ${p}`);
    }
    for (const n of notions) if (this.ancestors(n.id).has(n.id)) throw new Error(`${n.id}: prerequisite cycle`);
  }

  get(id: string): Notion {
    const n = this.notions.get(id);
    if (!n) throw new Error(`Unknown notion ${id}`);
    return n;
  }

  get all(): Notion[] {
    return [...this.notions.values()];
  }

  /** Everything this notion builds on, transitively. */
  ancestors(id: string): Set<string> {
    const out = new Set<string>();
    const stack = [...this.get(id).prerequisites];
    while (stack.length) {
      const p = stack.pop()!;
      if (out.has(p)) continue;
      out.add(p);
      stack.push(...this.get(p).prerequisites);
    }
    return out;
  }

  /** Everything that builds on this notion, transitively. */
  descendants(id: string): Set<string> {
    const out = new Set<string>();
    for (const n of this.notions.values()) if (this.ancestors(n.id).has(id)) out.add(n.id);
    return out;
  }

  /** Length of the longest prerequisite chain below a notion: 0 for foundations. */
  depth(id: string): number {
    const prerequisites = this.get(id).prerequisites;
    return prerequisites.length ? 1 + Math.max(...prerequisites.map((p) => this.depth(p))) : 0;
  }

  /**
   * What to learn to reach the targets: the missing targets plus their missing
   * prerequisites, foundations first. This is how a flagged gap becomes a plan.
   */
  learningPath(targets: readonly string[], known: (id: string) => boolean): Notion[] {
    const needed = new Set<string>();
    // Walk down from the targets; a known notion stops the walk (what it builds on is known too).
    const stack = [...targets];
    while (stack.length) {
      const id = stack.pop()!;
      if (needed.has(id) || known(id)) continue;
      needed.add(id);
      stack.push(...this.get(id).prerequisites);
    }
    return [...needed].map((id) => this.get(id)).sort((a, b) => this.depth(a.id) - this.depth(b.id) || a.title.localeCompare(b.title));
  }
}

export type Belief = 'known' | 'unknown' | 'unsure';

/**
 * Short placement check (after Knowledge Space Theory, the idea behind ALEKS):
 * one question can settle many notions. Passing a notion makes its
 * prerequisites likely known; failing it makes what builds on it likely
 * unknown. Each question goes to the notion that settles the most either way.
 *
 * The results are starting beliefs, not verdicts: the memory model takes over
 * as soon as the units are practised, and a notion marked known but failed
 * later simply comes back as a gap.
 */
export class PlacementCheck {
  private readonly belief = new Map<string, Belief>();
  private asked = 0;

  constructor(
    private readonly map: KnowledgeMap,
    scope: readonly string[],
    private readonly maxQuestions = 12,
  ) {
    for (const id of scope) this.belief.set(id, 'unsure');
  }

  /** The most informative notion to ask about next, or undefined when done. */
  next(): Notion | undefined {
    if (this.asked >= this.maxQuestions) return undefined;
    let best: { id: string; score: number; depth: number } | undefined;
    for (const [id, b] of this.belief) {
      if (b !== 'unsure') continue;
      const ifPass = 1 + this.countUnsure(this.map.ancestors(id));
      const ifFail = 1 + this.countUnsure(this.map.descendants(id));
      const score = Math.min(ifPass, ifFail);
      const depth = this.map.depth(id);
      if (!best || score > best.score || (score === best.score && depth < best.depth)) best = { id, score, depth };
    }
    return best ? this.map.get(best.id) : undefined;
  }

  record(id: string, passed: boolean): void {
    this.asked++;
    const spread = passed ? this.map.ancestors(id) : this.map.descendants(id);
    for (const n of [id, ...spread]) if (this.belief.has(n)) this.belief.set(n, passed ? 'known' : 'unknown');
  }

  result(): { known: string[]; unknown: string[]; unsure: string[]; asked: number } {
    const by = (b: Belief) => [...this.belief].filter(([, v]) => v === b).map(([id]) => id);
    return { known: by('known'), unknown: by('unknown'), unsure: by('unsure'), asked: this.asked };
  }

  private countUnsure(ids: Set<string>): number {
    let n = 0;
    for (const id of ids) if (this.belief.get(id) === 'unsure') n++;
    return n;
  }
}

export type NotionStatus = 'not-started' | 'learning' | 'fragile' | 'solid';

/**
 * A notion's status from the memories of its units: solid when every unit is
 * stable for weeks, fragile when any studied unit has slipped below the line.
 */
export function notionStatus(
  units: readonly ItemState[],
  memory: MemoryModel,
  now: Date,
  options = { fragileBelow: 0.8, solidFromDays: 21 },
): NotionStatus {
  const studied = units.filter((u) => u.card);
  if (studied.length === 0) return 'not-started';
  if (studied.some((u) => memory.retrievability(u.card, now) < options.fragileBelow)) return 'fragile';
  if (studied.length === units.length && studied.every((u) => u.card!.stability >= options.solidFromDays)) return 'solid';
  return 'learning';
}
