// `applyEvent` (src/store/fold.ts) is the frontend's own deterministic state
// fold — the same shape of risk as WS1's extractors (a pure function with
// branches per event kind) but had zero direct unit coverage; the 4 DoD
// tests only exercise it indirectly through two fixture replays. Added at
// the P5 review gate.
import { describe, it, expect } from 'vitest';
import { applyEvent } from '../src/store/fold';
import { emptySessionView } from '../src/types/api';
import type { ServerEnvelope } from '../src/transport/envelope';

function env(t: ServerEnvelope['t'], overrides: Partial<ServerEnvelope> = {}): ServerEnvelope {
  return { t, seq: 1, turn: null, ms: 0, d: {}, ...overrides };
}

describe('applyEvent — session.resumed', () => {
  it('resumes to "armed" when no turns exist yet', () => {
    const view = applyEvent(emptySessionView('s1'), env('session.resumed'));
    expect(view.state).toBe('armed');
  });

  it('resumes to "rendering_capturing" once a turn has been opened', () => {
    const opened = applyEvent(
      emptySessionView('s1'),
      env('turn.opened', { turn: 0, d: { turn_index: 0, speaker: 'clinician' } }),
    );
    const resumed = applyEvent(opened, env('session.resumed'));
    expect(resumed.state).toBe('rendering_capturing');
  });
});

describe('applyEvent — degrade level tracking', () => {
  it('max tracks the highest level seen and survives a later degraded.exited', () => {
    let view = emptySessionView('s1');
    view = applyEvent(view, env('degraded.entered', { d: { level: 2 } }));
    view = applyEvent(view, env('degraded.entered', { d: { level: 4 } }));
    expect(view.degrade).toEqual({ level: 4, max: 4, reason: null });

    view = applyEvent(view, env('degraded.entered', { d: { level: 1 } }));
    expect(view.degrade.level).toBe(1);
    expect(view.degrade.max).toBe(4); // a drop in current level must not lower the session-max

    view = applyEvent(view, env('degraded.exited'));
    expect(view.degrade.level).toBe(0);
    expect(view.degrade.max).toBe(4); // exiting degrade clears current level, not the historical max
  });
});

describe('applyEvent — unknown event kinds', () => {
  it('counts repeated unknown kinds instead of throwing', () => {
    let view = emptySessionView('s1');
    // @ts-expect-error deliberately an event kind the fold switch does not know about
    view = applyEvent(view, env('made.up.kind'));
    // @ts-expect-error same as above, a second time
    view = applyEvent(view, env('made.up.kind'));
    expect(view.unknownKinds['made.up.kind']).toBe(2);
  });
});

describe('applyEvent — lastSeq', () => {
  it('does not regress lastSeq for a seq<=0 envelope (e.g. a replayed hello frame)', () => {
    let view = emptySessionView('s1');
    view = applyEvent(view, env('turn.opened', { seq: 5, turn: 0, d: { turn_index: 0 } }));
    expect(view.lastSeq).toBe(5);
    view = applyEvent(view, env('hello', { seq: 0 }));
    expect(view.lastSeq).toBe(5);
  });
});

describe('applyEvent — out-of-order turns', () => {
  it('keeps turns sorted by index regardless of arrival order', () => {
    let view = emptySessionView('s1');
    view = applyEvent(view, env('turn.opened', { turn: 2, d: { turn_index: 2 } }));
    view = applyEvent(view, env('turn.opened', { turn: 0, d: { turn_index: 0 } }));
    view = applyEvent(view, env('turn.opened', { turn: 1, d: { turn_index: 1 } }));
    expect(view.turns.map((t) => t.index)).toEqual([0, 1, 2]);
  });
});
