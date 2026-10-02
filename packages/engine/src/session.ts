import type { PlannedItem, SessionPlan } from './planner.ts';
import { DEFAULT_TUNING, type Tuning } from './tuning.ts';
import type { Attempt } from './types.ts';

export type SessionStep =
  | { type: 'ask'; item: PlannedItem; retry: boolean }
  | { type: 'done'; reason: 'plan-complete' | 'time-budget' | 'child-stopped' | 'ease-off'; message: string };

export interface SessionResult {
  item: PlannedItem;
  attempt: Attempt;
  /** Second try within the same session: shown to help, not sent to the memory model. */
  retry: boolean;
}

/** After `easeOffAfterMisses` misses in a row, slip in an easier unit; after `stopAfterMisses`, end kindly. */
export type SessionRules = Tuning['session'];

/**
 * Runs one session from a plan and adapts inside it: missed units come back
 * once at the end, a run of misses brings an easier unit, and the session ends
 * when the time budget is used, whatever is left.
 */
export class SessionRunner {
  readonly results: SessionResult[] = [];
  private readonly queue: Array<{ item: PlannedItem; retry: boolean }>;
  private elapsedSeconds = 0;
  private missStreak = 0;
  private stopped = false;

  constructor(
    plan: SessionPlan,
    private readonly budgetSeconds: number,
    private readonly rules: SessionRules = DEFAULT_TUNING.session,
  ) {
    this.queue = plan.items.map((item) => ({ item, retry: false }));
  }

  next(): SessionStep {
    if (this.stopped) {
      return { type: 'done', reason: 'child-stopped', message: 'Stopped. Everything left moves to another day.' };
    }
    if (this.missStreak >= this.rules.stopAfterMisses) {
      return {
        type: 'done',
        reason: 'ease-off',
        message: 'Tough set today. Stopping here is the right call; these come back with a new explanation.',
      };
    }
    if (this.elapsedSeconds >= this.budgetSeconds) {
      return { type: 'done', reason: 'time-budget', message: "That's today's plan done. The rest moves to another day." };
    }
    if (this.queue.length === 0) {
      return { type: 'done', reason: 'plan-complete', message: "That's it for today." };
    }
    if (this.missStreak >= this.rules.easeOffAfterMisses) this.moveEasiestToFront();
    const { item, retry } = this.queue.shift()!;
    return { type: 'ask', item, retry };
  }

  answer(item: PlannedItem, attempt: Attempt, seconds: number, retry = false): void {
    this.elapsedSeconds += seconds;
    this.results.push({ item, attempt, retry });
    if (attempt.correct) {
      this.missStreak = 0;
      return;
    }
    this.missStreak++;
    if (!retry) this.queue.push({ item, retry: true });
  }

  /** The child can always stop, with no penalty. */
  stop(): void {
    this.stopped = true;
  }

  private moveEasiestToFront(): void {
    let best = -1;
    this.queue.forEach((entry, index) => {
      if (!entry.retry && (best < 0 || entry.item.recall > this.queue[best]!.item.recall)) best = index;
    });
    if (best > 0) this.queue.unshift(...this.queue.splice(best, 1));
  }
}
