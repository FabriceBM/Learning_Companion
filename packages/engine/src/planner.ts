import { probeLevelFor } from './grading.ts';
import { MemoryModel } from './memory.ts';
import { DEFAULT_RETENTION, nextGoal, targetRetention, type RetentionPolicy } from './retention.ts';
import { addDays, daysBetween, startOfDay } from './time.ts';
import type { Goal, ItemState, KnowledgeUnit, LearnerProfile, ProbeLevel } from './types.ts';

export interface PlannedItem {
  kuId: string;
  subject: string;
  title: string;
  kind: 'review' | 'new';
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
  /**
   * Due reviews that did not fit in the budget. They stay due and are
   * re-prioritised tomorrow. This is never shown to the child as a debt.
   */
  deferred: number;
  subjects: string[];
}

export interface PlanInput {
  learner: LearnerProfile;
  items: readonly ItemState[];
  goals: readonly Goal[];
  now: Date;
  memory: MemoryModel;
  policy?: RetentionPolicy;
}

const IMPORTANCE_WEIGHT = { 1: 0.7, 2: 1, 3: 1.4 } as const;
/** A prerequisite counts as known when its predicted recall is at least this. */
const PREREQUISITE_RECALL = 0.8;

/**
 * Build today's session: a finite list that fits the time budget.
 *
 * 1. Due reviews, most at risk first (importance and close tests weigh more).
 * 2. New units only if every due review fits, only when their prerequisites are
 *    known, and fewer of them when recent accuracy is low.
 * 3. Subjects interleaved; open and close on a unit the child probably knows.
 */
export function planSession(input: PlanInput): SessionPlan {
  const { learner, items, goals, now, memory } = input;
  const policy = input.policy ?? DEFAULT_RETENTION;
  const budget = learner.dailyBudgetMinutes * 60;
  const endOfToday = addDays(startOfDay(now), 1);

  const due = items
    .filter((i) => i.card && i.card.due.getTime() < endOfToday.getTime())
    .map((item) => {
      const recall = memory.retrievability(item.card, now);
      const target = targetRetention(item.ku, goals, now, policy);
      const goal = nextGoal(item.ku, goals, now);
      const daysToGoal = goal ? daysBetween(now, goal.date) : Infinity;
      const goalBoost = 1 + Math.max(0, policy.testWindowDays - daysToGoal) / policy.testWindowDays;
      const priority = IMPORTANCE_WEIGHT[item.ku.importance] * goalBoost * Math.max(0.01, target - recall + 0.05);
      return { item, recall, goal, priority };
    })
    .sort((a, b) => b.priority - a.priority);

  const chosen: PlannedItem[] = [];
  let used = 0;
  let deferred = 0;

  for (const { item, recall, goal } of due) {
    const level = probeLevelFor(item.ku.kind, item.card);
    const seconds = learner.secondsPerProbe[level];
    if (used + seconds > budget) {
      deferred++;
      continue;
    }
    chosen.push({
      kuId: item.ku.id,
      subject: item.ku.subject,
      title: item.ku.title,
      kind: 'review',
      level,
      recall,
      seconds,
      why: whyReview(item, recall, goal, now),
    });
    used += seconds;
  }

  if (deferred === 0) {
    const throttle = learner.recentAccuracy < 0.7 ? 0 : learner.recentAccuracy < 0.8 ? 0.5 : 1;
    const newCap = Math.floor(learner.maxNewPerDay * throttle);
    const known = prerequisiteCheck(items, memory, now);
    const fresh = items
      .map((item, order) => ({ item, order, goal: nextGoal(item.ku, goals, now) }))
      .filter(({ item }) => !item.card && known(item.ku))
      .sort(
        (a, b) =>
          (a.goal?.date.getTime() ?? Infinity) - (b.goal?.date.getTime() ?? Infinity) ||
          b.item.ku.importance - a.item.ku.importance ||
          a.order - b.order,
      );

    for (const { item, goal } of fresh.slice(0, newCap)) {
      // First meeting: the child studies the card, then answers it once.
      const seconds = learner.secondsPerProbe.recognize * 2;
      if (used + seconds > budget) break;
      chosen.push({
        kuId: item.ku.id,
        subject: item.ku.subject,
        title: item.ku.title,
        kind: 'new',
        level: 'recognize',
        recall: 0,
        seconds,
        why: goal ? `New, counts for ${goal.title}` : 'New from your latest lesson',
      });
      used += seconds;
    }
  }

  return {
    items: arrange(chosen),
    minutes: Math.ceil(used / 60),
    deferred,
    subjects: [...new Set(chosen.map((c) => c.subject))],
  };
}

function prerequisiteCheck(items: readonly ItemState[], memory: MemoryModel, now: Date) {
  const byId = new Map(items.map((i) => [i.ku.id, i]));
  return (ku: KnowledgeUnit) =>
    ku.prerequisites.every((id) => {
      const prerequisite = byId.get(id);
      // A prerequisite outside the learner's units (e.g. from a previous year) is assumed known.
      if (!prerequisite) return true;
      return memory.retrievability(prerequisite.card, now) >= PREREQUISITE_RECALL;
    });
}

function whyReview(item: ItemState, recall: number, goal: Goal | undefined, now: Date): string {
  const last = item.card?.last_review;
  const days = last ? Math.round(daysBetween(last, now)) : 0;
  const seen = days <= 0 ? 'Seen today' : days === 1 ? 'Seen yesterday' : `Seen ${days} days ago`;
  const parts = [seen, `recall now about ${Math.round(recall * 100)}%`];
  if (goal) {
    const inDays = Math.ceil(daysBetween(now, goal.date));
    parts.push(`${goal.title} in ${inDays} day${inDays === 1 ? '' : 's'}`);
  }
  return parts.join(' · ');
}

/**
 * Order the session: an easy opener, subjects interleaved (helps telling
 * similar things apart), and a likely success at the end so the session closes
 * on a good note.
 */
function arrange(items: PlannedItem[]): PlannedItem[] {
  const reviews = items.filter((i) => i.kind === 'review').sort((a, b) => b.recall - a.recall);
  const opener = reviews.shift();
  const closer = reviews.shift();
  const middle = interleave([...reviews, ...items.filter((i) => i.kind === 'new')], opener?.subject);
  return [opener, ...middle, closer].filter((i): i is PlannedItem => i !== undefined);
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
