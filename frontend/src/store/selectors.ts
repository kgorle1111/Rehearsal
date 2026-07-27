// 10-frontend-spec.md §5.4 — derived read models over SessionView.
import { computed } from './signal';
import type { Signal } from './signal';
import type { SessionView } from '../types/api';

export type TurnState = 'clinician' | 'patient' | 'yours' | 'processing' | null;

export function turnStateOf(view: SessionView): TurnState {
  switch (view.state) {
    case 'source_speaking':
      return view.turns.at(-1)?.speaker === 'patient' ? 'patient' : 'clinician';
    case 'awaiting_rendering':
    case 'rendering_capturing':
      return 'yours';
    case 'turn_closing':
      return 'processing';
    default:
      return null;
  }
}

export function directionOf(view: SessionView): 'en->es' | 'es->en' | null {
  const t = view.turns.find((t) => t.index === view.turnIndex);
  return t?.direction ?? null;
}

export function scoreSummaryOf(view: SessionView) {
  let clean = 0;
  let withFindings = 0;
  let critical = 0;
  let unscored = 0;
  for (const t of view.turns) {
    if (!t.verdict) {
      unscored++;
      continue;
    }
    if (t.verdict.nCritical > 0) critical++;
    if (t.verdict.nCritical + t.verdict.nNonCritical > 0) withFindings++;
    else clean++;
  }
  return { clean, withFindings, critical, unscored };
}

export function makeSelectors(view: Signal<SessionView>) {
  return {
    turnState: computed(() => turnStateOf(view())),
    direction: computed(() => directionOf(view())),
    canRequestRepeat: computed(() => turnStateOf(view()) !== null && view().state !== 'paused'),
    canPause: computed(() => view().mode !== 'assessment'),
    scoreSummary: computed(() => scoreSummaryOf(view())),
  };
}
