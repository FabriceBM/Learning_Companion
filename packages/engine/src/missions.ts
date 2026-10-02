import type { Focus } from './planner.ts';
import { MemoryModel } from './memory.ts';
import { isDue } from './day.ts';
import { daysBetween } from './time.ts';
import { DEFAULT_TUNING, type Tuning } from './tuning.ts';
import type { Goal, ItemState } from './types.ts';

/**
 * A mission is what the learner chooses to work on. The app suggests and
 * ranks; the learner picks. A mission session goes entirely to its units.
 *
 * by-heart: a text or a figure to learn word for word (use case 1, by-heart.ts)
 * pushed:   a notion parents pushed to the app, with the prerequisites it needs (use case 2)
 * test:     everything a dated test covers
 * topic:    anything chosen freely (a subject, a lesson, a notion)
 * mixed:    no focus: review whatever is due, interleaved (keeps everything fresh)
 */
export interface Mission {
  id: string;
  kind: 'by-heart' | 'pushed' | 'test' | 'topic' | 'mixed';
  title: string;
  /** Units in scope; empty for a mixed review. */
  kuIds: string[];
  goal?: Goal;
  /** Who pushed it, shown on the card ("pushed by your parents"). */
  pushedBy?: string;
}

export function testMission(goal: Goal, items: readonly ItemState[]): Mission {
  return { id: `test:${goal.id}`, kind: 'test', title: goal.title, goal, kuIds: items.filter((i) => i.ku.goalIds.includes(goal.id)).map((i) => i.ku.id) };
}

/** Use case 2: a notion parents pushed, as a learning path from KnowledgeMap.learningPath(). */
export function pushedMission(id: string, title: string, notionIds: readonly string[], items: readonly ItemState[], pushedBy?: string, goal?: Goal): Mission {
  const notions = new Set(notionIds);
  return { id: `pushed:${id}`, kind: 'pushed', title, pushedBy, goal, kuIds: items.filter((i) => i.ku.notionId && notions.has(i.ku.notionId)).map((i) => i.ku.id) };
}

/** Use case 1: a text or figure to learn by heart (units from byHeartUnits / figureUnits), optionally for a recitation date. */
export function byHeartMission(id: string, title: string, kuIds: readonly string[], goal?: Goal): Mission {
  return { id: `by-heart:${id}`, kind: 'by-heart', title, goal, kuIds: [...kuIds] };
}

export function topicMission(id: string, title: string, items: readonly ItemState[], pick: (i: ItemState) => boolean): Mission {
  return { id: `topic:${id}`, kind: 'topic', title, kuIds: items.filter(pick).map((i) => i.ku.id) };
}

export const MIXED_REVIEW: Mission = { id: 'mixed', kind: 'mixed', title: 'Keep everything fresh', kuIds: [] };

/** What the planner needs; undefined for a mixed review. */
export function toFocus(mission: Mission): Focus | undefined {
  return mission.kind === 'mixed' ? undefined : { missionId: mission.id, kuIds: new Set(mission.kuIds) };
}

export interface MissionProgress {
  total: number;
  started: number;
  /** Units whose memory is stable enough to leave the mission (see tuning.mission). */
  secure: number;
  /** Mean predicted recall over the scope, on the test day for a test mission (unstarted units count 0). */
  readiness: number;
  complete: boolean;
}

export function missionProgress(
  mission: Mission,
  items: readonly ItemState[],
  memory: MemoryModel,
  now: Date,
  tuning: Tuning = DEFAULT_TUNING,
): MissionProgress {
  const scope = new Set(mission.kuIds);
  const units = items.filter((i) => scope.has(i.ku.id));
  const at = mission.goal && mission.goal.date > now ? mission.goal.date : now;
  const secure = units.filter((i) => i.card && i.card.stability >= tuning.mission.secureStabilityDays).length;
  const readiness = units.length ? units.reduce((s, i) => s + memory.retrievability(i.card, at), 0) / units.length : 0;
  return {
    total: units.length,
    started: units.filter((i) => i.card).length,
    secure,
    readiness,
    complete: units.length > 0 && secure === units.length,
  };
}

export interface Suggestion {
  mission: Mission;
  score: number;
  reason: string;
  progress: MissionProgress;
}

/**
 * Rank missions for the learner to choose from: a close test that isn't ready
 * comes first, then gaps a parent flagged, then topics; a mixed review rises
 * as reviews pile up. The learner can always pick something else.
 */
export function suggestMissions(
  missions: readonly Mission[],
  items: readonly ItemState[],
  memory: MemoryModel,
  now: Date,
  tuning: Tuning = DEFAULT_TUNING,
): Suggestion[] {
  const dueCount = items.filter((i) => i.card && isDue(i.card, now)).length;
  return missions
    .map((mission) => {
      const progress = missionProgress(mission, items, memory, now, tuning);
      if (mission.kind === 'mixed') {
        return { mission, progress, score: (0.7 * dueCount) / (dueCount + 15), reason: `${dueCount} reviews due across subjects` };
      }
      const notSecure = progress.total ? 1 - progress.secure / progress.total : 0;
      if (mission.goal) {
        const days = Math.max(0.5, daysBetween(now, mission.goal.date));
        const window = tuning.retention.testWindowDays;
        return {
          mission,
          progress,
          // Inside the test window a test leads; further out it competes on how unready it is.
          score: (days <= window ? 0.5 : 0.2) + (1 - progress.readiness) * Math.min(1, window / days),
          reason: `In ${Math.ceil(days)} day${Math.ceil(days) === 1 ? '' : 's'} · ${Math.round(progress.readiness * 100)}% ready`,
        };
      }
      const label = mission.kind === 'pushed' && mission.pushedBy ? `Pushed by ${mission.pushedBy}` : mission.kind === 'by-heart' ? 'To learn by heart' : 'Your choice';
      const weight = { pushed: 0.6, 'by-heart': 0.5, test: 0.5, topic: 0.3 }[mission.kind];
      return {
        mission,
        progress,
        score: notSecure * weight,
        reason: `${label} · ${progress.secure} of ${progress.total} secure`,
      };
    })
    .filter((s) => !s.progress.complete || s.mission.kind === 'mixed')
    .sort((a, b) => b.score - a.score);
}
