// 10-frontend-spec.md §6.2, mirroring 11-backend-api.md §5.2-5.4.
// ServerEnvelope.t is exactly the event `kind` plus five transport frames.

export type EventKind =
  | 'hello'
  | 'gap.begin'
  | 'gap.end'
  | 'pong'
  | 'error'
  | 'session.started'
  | 'turn.opened'
  | 'source.emitted'
  | 'tts.started'
  | 'tts.finished'
  | 'tts.interrupted'
  | 'capture.started'
  | 'partial.transcript'
  | 'capture.ended'
  | 'turn.committed'
  | 'rendering.emitted'
  | 'score.pending'
  | 'score.ready'
  | 'score.partial'
  | 'verdict.merged'
  | 'coach.emitted'
  | 'coach.suppressed'
  | 'degraded.entered'
  | 'degraded.exited'
  | 'budget.exceeded'
  | 'host.restarted'
  | 'session.paused'
  | 'session.resumed'
  | 'session.ended';

export interface ServerEnvelope {
  t: EventKind;
  seq: number;
  turn: number | null;
  ms: number;
  d: Record<string, unknown>;
}

export type ClientEnvelope =
  | { t: 'hello'; d: { last_seq: number | null; client_build: string } }
  | { t: 'start'; d: Record<string, never> }
  | { t: 'pause'; d: Record<string, never> }
  | { t: 'resume'; d: Record<string, never> }
  | { t: 'abort'; d: { reason: string } }
  | { t: 'repeat'; d: { turn: number } }
  | { t: 'ack'; d: { seq: number } }
  | { t: 'ping'; d: Record<string, never> }
  | { t: 'coach.dismiss'; d: { turn_index: number } };

// kn: minimal structural guard, not a full schema validator — sufficient for the trust
// boundary rule (§6.2: malformed envelopes are dropped, never partially applied).
export function isServerEnvelope(x: unknown): x is ServerEnvelope {
  if (typeof x !== 'object' || x === null) return false;
  const o = x as Record<string, unknown>;
  return (
    typeof o.t === 'string' &&
    typeof o.seq === 'number' &&
    (typeof o.turn === 'number' || o.turn === null) &&
    typeof o.ms === 'number' &&
    typeof o.d === 'object' &&
    o.d !== null
  );
}
