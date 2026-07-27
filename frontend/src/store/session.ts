// 10-frontend-spec.md §5.2 — SessionView is folded from the event stream; the client copy is
// disposable. §3.5 — coach interjections buffer until the turn.closed -> turn.opened boundary.
import { signal } from './signal';
import { applyEvent } from './fold';
import type { ServerEnvelope } from '../transport/envelope';
import { emptySessionView, type Coach, type SessionView } from '../types/api';

export function createSessionStore(sessionId: string) {
  const view = signal<SessionView>(emptySessionView(sessionId));
  const replaying = signal(false);
  let pendingCoach: Coach | null = null;
  let prevState = view.peek().state;

  function apply(env: ServerEnvelope): void {
    if (env.t === 'coach.emitted') {
      // §3.5: buffered, not applied immediately, and dropped (never queued) on a second arrival.
      const d = env.d as Record<string, unknown>;
      pendingCoach = {
        turnIndex: env.turn ?? (d.turn_index as number) ?? view.peek().turnIndex,
        kind: String(d.kind ?? ''),
        text: String(d.text ?? ''),
        priority: String(d.priority ?? 'normal'),
      };
      return;
    }
    const next = applyEvent(view.peek(), env);
    view.set(next);
    if (env.t === 'turn.opened' && prevState !== next.state) {
      if (pendingCoach && next.mode === 'practice') {
        view.set({ ...view.peek(), pendingCoach });
      }
      pendingCoach = null;
    }
    prevState = next.state;
  }

  function applyMany(envs: ServerEnvelope[]): void {
    for (const env of envs) apply(env);
  }

  return { view, replaying, apply, applyMany };
}

export type SessionStore = ReturnType<typeof createSessionStore>;
