import { isDue } from './day.ts';
import { probeLevelFor } from './grading.ts';
import { MemoryModel } from './memory.ts';
import { nextGoal, targetRetention } from './retention.ts';
import { daysBetween } from './time.ts';
import { DEFAULT_TUNING, type Tuning } from './tuning.ts';
import type { Goal, ItemState, KnowledgeUnit, LearnerProfile, ProbeLevel } from './types.ts';

export interface PlannedItem {
  kuId: string;
  subject: string;
  title: string;
  /**
   * review: due today · new: first meeting · repair: a weak prerequisite of the
   * mission · practice: extra practice on a mission unit that is not secure yet
   */
  kind: 'review' | 'new' | 'repair' | 'practice';
  level: ProbeLevel;
  /** Predicted recall right now (0 for a new unit). */
  recall: number;
  seconds: number;
  /** One line shown under "Why this card?". */
  why: string;
}

export interface SessionPlan {
  items: PlannedItem[];
  minutes: number;
  /** Due reviews in scope that did not fit. Re-prioritised next session; never shown as a debt. */
  deferred: number;
  /** Due reviews outside the mission, waiting for a later session. */
  waiting: number;
  subjects: string[];
  missionId?: string;
}

/** A mission narrows the session to its units (see missions.ts). */
export interface Focus {
  missionId: string;
  kuIds: ReadonlySet<string>;
}

export interface PlanInput {
  learner: LearnerProfile;
  items: readonly ItemState[];
  goals: readonly Goal[];
  now: Date;
  memory: MemoryModel;
  tuning?: Tuning;
  /** New units already introduced in today's earlier sessions. */
  newToday?: number;
  /** The mission the learner chose; without one, the session reviews everything due. */
  focus?: Focus;
  /** From the concentration profile: false groups a mixed review by subject (switching costs this learner too much). */
  interleaveMixed?: boolean;
}

/**
 * Build one session: a finite list that fits the session length.
 *
 * Without a mission (mixed review):
 *   1. due reviews, most at risk first; 2. new units if every due review fits;
 *   3. subjects interleaved, opening and closing on units the child probably knows.
 *
 * With a mission (focus), the whole session goes to it:
 *   0. weak prerequisites of the mission repaired first;
 *   1. due mission reviews; 2. new mission units in prerequisite order;
 *   3. extra practice on mission units that are not secure yet;
 *   ordered foundations first, one notion at a time, ending on a likely success.
 *   Other due reviews wait (they are counted, not lost).
 */
export function planSession(input: PlanInput): SessionPlan {
  const { learner, items, goals, now, memory, focus } = input;
  const t = input.tuning ?? DEFAULT_TUNING;
  const budget = learner.sessionMinutes * 60;
  const missionBudget = focus ? budget * t.mission.focusShare : budget;
  const byId = new Map(items.map((i) => [i.ku.id, i]));
  const inScope = (i: ItemState) => !focus || focus.kuIds.has(i.ku.id);
  const depth = depthOf(byId);

  const chosen: PlannedItem[] = [];
  const taken = new Set<string>();
  let used = 0;

  const take = (item: ItemState, kind: PlannedItem['kind'], why: string, limit: number): boolean => {
    const level: ProbeLevel = kind === 'new' ? 'recognize' : probeLevelFor(item.ku.kind, item.card, t.ladder);
    const seconds = kind === 'new' ? learner.secondsPerProbe.recognize * t.planner.newUnitCost : learner.secondsPerProbe[level];
    if (used + seconds > limit) return false;
    const recall = memory.retrievability(item.card, now);
    chosen.push({ kuId: item.ku.id, subject: item.ku.subject, title: item.ku.title, kind, level, recall, seconds, why });
    taken.add(item.ku.id);
    used += seconds;
    return true;
  };

  // 0. Mission: repair weak foundations first.
  if (focus) {
    const scopeItems = items.filter(inScope);
    const prerequisites = closure(scopeItems.flatMap((i) => i.ku.prerequisites), byId);
    const weak = [...prerequisites]
      .map((id) => byId.get(id)!)
      .filter((p) => p.card && memory.retrievability(p.card, now) < t.mission.repairBelowRecall)
      .sort((a, b) => depth(a.ku.id) - depth(b.ku.id));
    for (const p of weak) {
      const dependent = scopeItems.find((i) => closure(i.ku.prerequisites, byId).has(p.ku.id));
      take(p, 'repair', `Needed for "${dependent?.ku.title ?? 'your mission'}": recall is down to ${pct(memory.retrievability(p.card, now))}`, missionBudget);
    }
  }

  // 1. Due reviews, most at risk first.
  const due = items
    .filter((i) => i.card && isDue(i.card, now) && !taken.has(i.ku.id))
    .map((item) => ({ item, ...urgency(item, goals, now, memory, t) }));
  let deferred = 0;
  for (const d of due.filter((d) => inScope(d.item)).sort((a, b) => b.priority - a.priority)) {
    if (!take(d.item, 'review', whyReview(d.item, d.recall, d.goal, now), missionBudget)) deferred++;
  }

  // 2. New units, only if every due review fits.
  if (deferred === 0) {
    const throttle = learner.recentAccuracy < t.planner.pauseNewBelow ? 0 : learner.recentAccuracy < t.planner.halveNewBelow ? 0.5 : 1;
    const newCap = Math.max(0, Math.floor(learner.maxNewPerDay * throttle) - (input.newToday ?? 0));
    const introduced = new Set<string>();
    const known = (ku: KnowledgeUnit) =>
      ku.prerequisites.every((id) => {
        const p = byId.get(id);
        // A prerequisite outside the learner's units (learned long ago) is assumed known.
        if (!p || memory.retrievability(p.card, now) >= t.planner.prerequisiteRecall) return true;
        // In a mission, a notion is learned in one go: a unit may follow a prerequisite
        // of the same notion introduced earlier in this session.
        return Boolean(focus && introduced.has(id) && p.ku.notionId && p.ku.notionId === ku.notionId);
      });
    const fresh = items
      .map((item, order) => ({ item, order, goal: nextGoal(item.ku, goals, now) }))
      .filter(({ item }) => !item.card && inScope(item))
      .sort(
        (a, b) =>
          (a.goal?.date.getTime() ?? Infinity) - (b.goal?.date.getTime() ?? Infinity) ||
          (focus ? depth(a.item.ku.id) - depth(b.item.ku.id) : 0) ||
          b.item.ku.importance - a.item.ku.importance ||
          a.order - b.order,
      );
    // Repeated passes let a unit follow its same-notion prerequisite within the session.
    let added = true;
    while (added && introduced.size < newCap) {
      added = false;
      for (const { item, goal } of fresh) {
        if (introduced.size >= newCap) break;
        if (introduced.has(item.ku.id) || !known(item.ku)) continue;
        const why = focus ? 'New in your mission' : goal ? `New, counts for ${goal.title}` : 'New from your latest lesson';
        if (!take(item, 'new', why, missionBudget)) break;
        introduced.add(item.ku.id);
        added = true;
      }
    }
  }

  // 3. Mission: extra practice on units that are not secure yet, until the session is full.
  if (focus) {
    const practice = items
      .filter((i) => i.card && inScope(i) && !taken.has(i.ku.id) && i.card.stability < t.mission.secureStabilityDays)
      .sort((a, b) => memory.retrievability(a.card, now) - memory.retrievability(b.card, now));
    for (const p of practice) take(p, 'practice', 'Not secure yet: extra practice for your mission', missionBudget);

    // Full focus by default: a short mission makes a short session. Below 100%,
    // the remaining share keeps the most at-risk other reviews alive.
    if (t.mission.focusShare < 1) {
      for (const d of due.filter((d) => !inScope(d.item) && !taken.has(d.item.ku.id)).sort((a, b) => b.priority - a.priority)) {
        take(d.item, 'review', whyReview(d.item, d.recall, d.goal, now), budget);
      }
    }
  }

  const waiting = focus ? due.filter((d) => !inScope(d.item) && !taken.has(d.item.ku.id)).length : 0;
  return {
    items: focus ? arrangeFocused(chosen, depth) : arrangeMixed(chosen, input.interleaveMixed ?? true),
    minutes: Math.ceil(used / 60),
    deferred,
    waiting,
    subjects: [...new Set(chosen.map((c) => c.subject))],
    missionId: focus?.missionId,
  };
}

function urgency(item: ItemState, goals: readonly Goal[], now: Date, memory: MemoryModel, t: Tuning) {
  const recall = memory.retrievability(item.card, now);
  const target = targetRetention(item.ku, goals, now, t.retention);
  const goal = nextGoal(item.ku, goals, now);
  const daysToGoal = goal ? daysBetween(now, goal.date) : Infinity;
  const window = t.retention.testWindowDays;
  const goalBoost = 1 + (t.planner.testBoost * Math.max(0, window - daysToGoal)) / window;
  const weight = [0, t.planner.weightNiceToKnow, t.planner.weightExpected, t.planner.weightFoundational][item.ku.importance]!;
  return { recall, goal, priority: weight * goalBoost * Math.max(0.01, target - recall + t.planner.riskFloor) };
}

/** All transitive prerequisites of the given unit ids (only those the learner has). */
function closure(ids: readonly string[], byId: Map<string, ItemState>): Set<string> {
  const seen = new Set<string>();
  const stack = [...ids];
  while (stack.length) {
    const id = stack.pop()!;
    const item = byId.get(id);
    if (!item || seen.has(id)) continue;
    seen.add(id);
    stack.push(...item.ku.prerequisites);
  }
  return seen;
}

/** Length of the longest prerequisite chain below a unit: 0 for foundations. */
function depthOf(byId: Map<string, ItemState>) {
  const memo = new Map<string, number>();
  const depth = (id: string, guard = new Set<string>()): number => {
    if (memo.has(id)) return memo.get(id)!;
    const item = byId.get(id);
    if (!item || guard.has(id)) return 0;
    guard.add(id);
    const d = Math.max(-1, ...item.ku.prerequisites.map((p) => depth(p, guard))) + 1;
    memo.set(id, d);
    return d;
  };
  return (id: string) => depth(id);
}

function whyReview(item: ItemState, recall: number, goal: Goal | undefined, now: Date): string {
  const last = item.card?.last_review;
  const hours = last ? (now.getTime() - last.getTime()) / 3_600_000 : 0;
  const days = Math.round(hours / 24);
  const seen = hours < 12 ? 'Seen earlier today: a second look after a break' : days === 1 ? 'Seen yesterday' : `Seen ${days} days ago`;
  const parts = [seen, `recall now about ${pct(recall)}`];
  if (goal) {
    const inDays = Math.ceil(daysBetween(now, goal.date));
    parts.push(`${goal.title} in ${inDays} day${inDays === 1 ? '' : 's'}`);
  }
  return parts.join(' · ');
}

const pct = (x: number) => `${Math.round(x * 100)}%`;

/**
 * Mixed review: an easy opener, subjects interleaved (telling similar things
 * apart is part of the skill), and a likely success to close on.
 */
function arrangeMixed(items: PlannedItem[], interleaveSubjects: boolean): PlannedItem[] {
  const reviews = items.filter((i) => i.kind === 'review').sort((a, b) => b.recall - a.recall);
  const opener = reviews.shift();
  const closer = reviews.shift();
  const rest = [...reviews, ...items.filter((i) => i.kind === 'new')];
  const middle = interleaveSubjects ? interleave(rest, opener?.subject) : [...rest].sort((a, b) => a.subject.localeCompare(b.subject));
  return [opener, ...middle, closer].filter((i): i is PlannedItem => i !== undefined);
}

/**
 * Mission: foundations first, then one notion at a time (blocked practice
 * suits a skill being acquired), ending on a likely success.
 */
function arrangeFocused(items: PlannedItem[], depth: (id: string) => number): PlannedItem[] {
  const rank = { repair: 0, review: 1, new: 2, practice: 3 } as const;
  const sorted = [...items].sort((a, b) =>
    a.kind === 'repair' || b.kind === 'repair'
      ? rank[a.kind] - rank[b.kind] || depth(a.kuId) - depth(b.kuId)
      : depth(a.kuId) - depth(b.kuId) || rank[a.kind] - rank[b.kind],
  );
  const reviews = sorted.filter((i) => i.kind === 'review' || i.kind === 'practice');
  const closer = reviews.length > 1 ? reviews.reduce((a, b) => (b.recall > a.recall ? b : a)) : undefined;
  return closer ? [...sorted.filter((i) => i !== closer), closer] : sorted;
}

function interleave(items: PlannedItem[], previousSubject?: string): PlannedItem[] {
  const queues = new Map<string, PlannedItem[]>();
  for (const item of items) {
    const queue = queues.get(item.subject) ?? [];
    queue.push(item);
    queues.set(item.subject, queue);
  }
  const out: PlannedItem[] = [];
  let last = previousSubject;
  while (out.length < items.length) {
    const open = [...queues.entries()].filter(([, q]) => q.length > 0).sort((a, b) => b[1].length - a[1].length);
    const [subject, queue] = open.find(([s]) => s !== last) ?? open[0]!;
    out.push(queue.shift()!);
    last = subject;
  }
  return out;
}
