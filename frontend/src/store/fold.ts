// 10-frontend-spec.md §5.3 — applyEvent is pure, imports nothing outside types/, and mirrors
// the subset of fold() in src/rehearsal/orchestrator/resume.py that the UI renders
// (03-system-architecture.md §8.3). Unknown event kinds are ignored but counted, never thrown on.
import type { ServerEnvelope } from '../transport/envelope';
import type {
  DegradeLevel,
  ErrorKind,
  Finding,
  SessionState,
  SessionView,
  TurnView,
} from '../types/api';

function turnAt(view: SessionView, index: number): TurnView {
  const existing = view.turns.find((t) => t.index === index);
  if (existing) return existing;
  const created: TurnView = {
    index,
    speaker: 'clinician',
    direction: 'en->es',
    source: null,
    rendering: null,
    partial: false,
    verdict: null,
    audioSha: null,
  };
  view.turns.push(created);
  view.turns.sort((a, b) => a.index - b.index);
  return created;
}

export function applyEvent(view: SessionView, env: ServerEnvelope): SessionView {
  const d = env.d as Record<string, unknown>;
  let next = view;
  if (env.seq > 0) next = { ...view, lastSeq: env.seq };

  switch (env.t) {
    case 'session.started': {
      const state = d.state as SessionState | undefined;
      return { ...next, state: state ?? next.state };
    }

    case 'turn.opened': {
      const turnIndex = (d.turn_index as number) ?? env.turn ?? next.turnIndex;
      const turns = [...next.turns];
      const view2: SessionView = { ...next, turns, turnIndex, state: 'source_speaking' };
      const t = turnAt(view2, turnIndex);
      t.speaker = (d.speaker as TurnView['speaker']) ?? t.speaker;
      t.direction = (d.direction as TurnView['direction']) ?? t.direction;
      return view2;
    }

    case 'source.emitted': {
      const turnIndex = env.turn ?? next.turnIndex;
      const view2: SessionView = { ...next, turns: [...next.turns] };
      const t = turnAt(view2, turnIndex);
      t.source = { text: String(d.text ?? ''), lang: (d.lang as 'en' | 'es') ?? 'en' };
      return view2;
    }

    case 'capture.started':
      return { ...next, state: 'rendering_capturing' };

    case 'turn.committed': {
      const turnIndex = env.turn ?? next.turnIndex;
      const view2: SessionView = { ...next, turns: [...next.turns], state: 'turn_closing' };
      const t = turnAt(view2, turnIndex);
      t.rendering = {
        text: String(d.text ?? ''),
        lang: (d.lang as 'en' | 'es') ?? (t.direction === 'en->es' ? 'es' : 'en'),
      };
      t.partial = Boolean(d.partial);
      t.audioSha = (d.audio_sha as string) ?? null;
      return view2;
    }

    case 'score.ready':
    case 'score.partial':
    case 'verdict.merged': {
      const turnIndex = env.turn ?? (d.turn_index as number) ?? next.turnIndex;
      const view2: SessionView = { ...next, turns: [...next.turns] };
      const t = turnAt(view2, turnIndex);
      const status: 'complete' | 'partial' | 'grader_unavailable' =
        env.t === 'score.partial' ? 'partial' : (d.status as any) ?? 'complete';
      t.verdict = {
        status,
        nCritical: Number(d.n_critical ?? 0),
        nNonCritical: Number(d.n_non_critical ?? 0),
        findings: (d.findings as Finding[]) ?? [],
        notAssessed: (d.not_assessed as ErrorKind[]) ?? [],
      };
      return view2;
    }

    case 'coach.emitted': {
      const turnIndex = env.turn ?? (d.turn_index as number) ?? next.turnIndex;
      return {
        ...next,
        pendingCoach: {
          turnIndex,
          kind: String(d.kind ?? ''),
          text: String(d.text ?? ''),
          priority: String(d.priority ?? 'normal'),
        },
      };
    }

    case 'coach.suppressed':
      return { ...next, pendingCoach: null };

    case 'degraded.entered': {
      const level = (d.level as DegradeLevel) ?? next.degrade.level;
      return {
        ...next,
        degrade: {
          level,
          max: (Math.max(next.degrade.max, level) as DegradeLevel) ?? level,
          reason: (d.human_reason as string) ?? (d.trigger as string) ?? null,
        },
      };
    }

    case 'degraded.exited':
      return { ...next, degrade: { ...next.degrade, level: 0, reason: null } };

    case 'session.paused':
      return { ...next, state: 'paused' };

    case 'session.resumed':
      return { ...next, state: next.turns.length ? 'rendering_capturing' : 'armed' };

    case 'session.ended': {
      const state = (d.state as SessionState) ?? 'debrief';
      return { ...next, state };
    }

    case 'hello':
    case 'gap.begin':
    case 'gap.end':
    case 'pong':
    case 'error':
    case 'tts.started':
    case 'tts.finished':
    case 'tts.interrupted':
    case 'partial.transcript':
    case 'capture.ended':
    case 'score.pending':
    case 'budget.exceeded':
    case 'host.restarted':
      return next;

    default: {
      const unknownKinds = { ...next.unknownKinds };
      unknownKinds[env.t] = (unknownKinds[env.t] ?? 0) + 1;
      return { ...next, unknownKinds };
    }
  }
}

export function foldAll(initial: SessionView, events: ServerEnvelope[]): SessionView {
  return events.reduce(applyEvent, initial);
}
