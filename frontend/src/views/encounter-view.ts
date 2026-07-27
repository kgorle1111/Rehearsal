// 09-ui-ux.md §5.3, 10-frontend-spec.md §3.2 — wires the existing encounter/* custom elements
// into the full triad-grid screen. Never reads a socket directly (§3.1 pattern followed by the
// components themselves): commands go out through opts.send, live state comes in through
// session.view via effect().
import { effect } from '../store/signal';
import type { SessionStore } from '../store/session';
import { makeSelectors } from '../store/selectors';
import { t } from '../i18n';
import { settings } from '../store/settings';
import type { ClientEnvelope } from '../transport/envelope';
import type { ConnectionStatus } from '../transport/ws';
import type { Signal } from '../store/signal';
import type { TextBlock } from '../types/api';
import '../components/encounter/connection-status';
import '../components/encounter/degrade-banner';
import '../components/encounter/directional-cue';
import '../components/encounter/level-meter';
import '../components/encounter/speaker-panel';
import '../components/encounter/transcript';
import '../components/encounter/turn-state';
import type { RehearsalConnectionStatus } from '../components/encounter/connection-status';
import type { RehearsalSpeakerPanel, PanelUtterance } from '../components/encounter/speaker-panel';
import type { RehearsalTranscript, TranscriptItem } from '../components/encounter/transcript';

export interface EncounterViewOptions {
  send?: (env: ClientEnvelope) => void;
  connectionStatus?: Signal<ConnectionStatus>;
  onExit?: () => void;
}

export function mountEncounterView(
  container: HTMLElement,
  session: SessionStore,
  opts: EncounterViewOptions = {},
): () => void {
  const sel = makeSelectors(session.view);
  container.innerHTML = '';
  container.className = 'encounter-view';

  const bar = document.createElement('header');
  bar.className = 'encounter-bar';
  const exitBtn = document.createElement('button');
  exitBtn.type = 'button';
  exitBtn.textContent = t('encounter.exit');
  exitBtn.addEventListener('click', () => opts.onExit?.());
  const scenarioLabel = document.createElement('span');
  const modeBadge = document.createElement('span');
  const turnLabel = document.createElement('span');
  bar.append(exitBtn, scenarioLabel, modeBadge, turnLabel);

  const connStatus = document.createElement('rehearsal-connection-status') as RehearsalConnectionStatus;
  const degradeBanner = document.createElement('rehearsal-degrade-banner');

  const grid = document.createElement('div');
  grid.className = 'triad-grid';

  const clinicianPanel = document.createElement('rehearsal-speaker-panel') as RehearsalSpeakerPanel;
  clinicianPanel.setAttribute('speaker', 'clinician');
  const patientPanel = document.createElement('rehearsal-speaker-panel') as RehearsalSpeakerPanel;
  patientPanel.setAttribute('speaker', 'patient');

  const centerCol = document.createElement('div');
  centerCol.className = 'stack';
  const turnState = document.createElement('rehearsal-turn-state');
  const cue = document.createElement('rehearsal-directional-cue');
  const levelMeter = document.createElement('rehearsal-level-meter');
  const yourTranscript = document.createElement('rehearsal-transcript') as RehearsalTranscript;
  centerCol.append(turnState, cue, levelMeter, yourTranscript);

  grid.append(clinicianPanel, centerCol, patientPanel);

  const liveRegion = document.createElement('div');
  liveRegion.className = 'sr-only';
  liveRegion.setAttribute('aria-live', 'polite');
  container.addEventListener('announce', (e) => {
    liveRegion.textContent = (e as CustomEvent<{ text: string }>).detail.text;
  });

  const actions = document.createElement('footer');
  actions.className = 'encounter-actions';
  const repeatBtn = document.createElement('button');
  repeatBtn.type = 'button';
  repeatBtn.textContent = t('encounter.repeat');
  repeatBtn.addEventListener('click', () => {
    opts.send?.({ t: 'repeat', d: { turn: session.view.peek().turnIndex } });
  });
  const notesBtn = document.createElement('button');
  notesBtn.type = 'button';
  notesBtn.textContent = t('encounter.notes');
  const endBtn = document.createElement('button');
  endBtn.type = 'button';
  endBtn.textContent = t('encounter.end');
  endBtn.addEventListener('click', () => opts.send?.({ t: 'abort', d: { reason: 'user_end' } }));
  actions.append(repeatBtn, notesBtn, endBtn);

  container.append(bar, connStatus, degradeBanner, grid, liveRegion, actions);

  const disposers: Array<() => void> = [];

  disposers.push(
    effect(() => {
      const view = session.view();
      scenarioLabel.textContent = view.scenario.title;
      modeBadge.textContent = t(`encounter.mode.${view.mode}`);
      turnLabel.textContent = view.turnIndex >= 0 ? t('encounter.turn.label', { n: view.turnIndex + 1 }) : '';
      degradeBanner.setAttribute('level', String(view.degrade.level));
      degradeBanner.setAttribute('reason', view.degrade.reason ?? '');

      const state = sel.turnState();
      turnState.setAttribute('state', state ?? '');
      const direction = sel.direction();
      turnState.setAttribute('direction', direction ?? '');
      turnState.setAttribute('reduced-motion', String(settings.peek().reducedMotion));
      cue.setAttribute('direction', direction ?? '');

      const clinicianItems: PanelUtterance[] = [];
      const patientItems: PanelUtterance[] = [];
      const yourItems: TranscriptItem[] = [];
      for (const turn of view.turns) {
        if (turn.source) {
          const item: PanelUtterance = { text: turn.source as TextBlock, index: turn.index };
          if (turn.speaker === 'clinician') clinicianItems.push(item);
          else patientItems.push(item);
        }
        if (turn.rendering) yourItems.push({ text: turn.rendering, index: turn.index });
      }
      clinicianPanel.utterances = clinicianItems;
      clinicianPanel.setAttribute('active', String(state === 'clinician'));
      patientPanel.utterances = patientItems;
      patientPanel.setAttribute('active', String(state === 'patient'));
      yourTranscript.items = yourItems;
    }),
  );

  if (opts.connectionStatus) {
    const statusSignal = opts.connectionStatus;
    disposers.push(
      effect(() => {
        connStatus.status = statusSignal();
      }),
    );
  }

  return () => {
    for (const d of disposers) d();
  };
}
