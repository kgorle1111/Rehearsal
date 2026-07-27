// BUILD.md WS8 DoD, priority 4 — replay a recorded event log against encounter-view and render
// report-view from a fixture, with no backend running, 0 console errors.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createSessionStore } from '../src/store/session';
import { mountEncounterView } from '../src/views/encounter-view';
import { mountReportView } from '../src/views/report-view';
import type { ServerEnvelope } from '../src/transport/envelope';
import type { SessionReport } from '../src/types/api';
import eventsFixture from './fixtures/session-events.json';
import reportFixture from './fixtures/session-report.json';

describe('fixture replay — no backend running', () => {
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
    document.body.innerHTML = '';
  });

  it('renders the encounter view from a replayed event log with 0 console errors', () => {
    const store = createSessionStore('sess-fixture-1');
    store.applyMany(eventsFixture as unknown as ServerEnvelope[]);

    expect(store.view().turns.length).toBe(2);
    expect(store.view().state).toBe('debrief');

    const container = document.createElement('div');
    document.body.appendChild(container);
    const cleanup = mountEncounterView(container, store);

    expect(container.querySelector('rehearsal-transcript')).toBeTruthy();
    expect(container.querySelector('rehearsal-speaker-panel[speaker="clinician"]')).toBeTruthy();
    expect(container.querySelector('rehearsal-speaker-panel[speaker="patient"]')).toBeTruthy();
    expect(errorSpy).not.toHaveBeenCalled();

    cleanup();
  });

  it('renders the report view from a fixture report with 0 console errors', () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const cleanup = mountReportView(container, reportFixture as unknown as SessionReport);

    expect(container.textContent).toContain('Substitution');
    expect(container.textContent).not.toContain('undefined');
    expect(errorSpy).not.toHaveBeenCalled();

    cleanup();
  });
});
