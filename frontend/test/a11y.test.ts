// BUILD.md WS8 DoD, priority 5 — axe-core scan against jsdom-rendered DOM, 0 violations.
// axe.run() works directly against a jsdom document (no headless browser needed) per the WS8
// brief. Views are mounted inside a <main> under a <nav> landmark, matching the real app shell
// (src/main.ts), so the "region" / landmark rules are exercised honestly rather than disabled.
import { describe, it, expect } from 'vitest';
import axe from 'axe-core';
import { createSessionStore } from '../src/store/session';
import { mountEncounterView } from '../src/views/encounter-view';
import { mountReportView } from '../src/views/report-view';
import type { ServerEnvelope } from '../src/transport/envelope';
import type { SessionReport } from '../src/types/api';
import eventsFixture from './fixtures/session-events.json';
import reportFixture from './fixtures/session-report.json';

function appShell(): HTMLElement {
  document.body.innerHTML = '';
  document.documentElement.lang = 'en';
  const nav = document.createElement('nav');
  nav.setAttribute('aria-label', 'Rehearsal');
  const link = document.createElement('a');
  link.href = '#/practice';
  link.textContent = 'Practice';
  nav.appendChild(link);
  const main = document.createElement('main');
  document.body.append(nav, main);
  return main;
}

describe('accessibility — axe-core scan', () => {
  it('encounter view has 0 violations', async () => {
    const main = appShell();
    const store = createSessionStore('sess-fixture-1');
    store.applyMany(eventsFixture as unknown as ServerEnvelope[]);
    mountEncounterView(main, store);

    const results = await axe.run(document.body);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  it('report view has 0 violations', async () => {
    const main = appShell();
    mountReportView(main, reportFixture as unknown as SessionReport);

    const results = await axe.run(document.body);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
});
