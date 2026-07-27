// BUILD.md WS8 DoD, priority 7 — no missing translation keys leaking into rendered text, for
// both en-US and es-MX. t() (src/i18n/index.ts) falls back to returning the raw dotted key on a
// cache miss, so a leaked key is a literal string like "report.turns.title" appearing in the DOM.
import { describe, it, expect, afterEach } from 'vitest';
import { createSessionStore } from '../src/store/session';
import { mountEncounterView } from '../src/views/encounter-view';
import { mountReportView } from '../src/views/report-view';
import { setLocale, keysFor, type Locale } from '../src/i18n';
import type { ServerEnvelope } from '../src/transport/envelope';
import type { SessionReport } from '../src/types/api';
import eventsFixture from './fixtures/session-events.json';
import reportFixture from './fixtures/session-report.json';

const KEY_LEAK_PATTERN = /\b[a-z]+(\.[a-zA-Z]+){2,}\b/;

describe('i18n — no missing-key leaks', () => {
  afterEach(async () => {
    await setLocale('en-US');
    document.body.innerHTML = '';
  });

  it('en-US and es-MX catalogs define exactly the same key set', () => {
    expect(keysFor('es-MX').slice().sort()).toEqual(keysFor('en-US').slice().sort());
  });

  for (const locale of ['en-US', 'es-MX'] as Locale[]) {
    it(`renders encounter + report views with no leaked keys for ${locale}`, async () => {
      await setLocale(locale);

      const store = createSessionStore('sess-fixture-1');
      store.applyMany(eventsFixture as unknown as ServerEnvelope[]);
      const encounterContainer = document.createElement('div');
      document.body.appendChild(encounterContainer);
      mountEncounterView(encounterContainer, store);

      const reportContainer = document.createElement('div');
      document.body.appendChild(reportContainer);
      mountReportView(reportContainer, reportFixture as unknown as SessionReport);

      const text = `${encounterContainer.textContent ?? ''}\n${reportContainer.textContent ?? ''}`;
      const leak = KEY_LEAK_PATTERN.exec(text);
      expect(leak, `possible leaked i18n key: ${leak?.[0]}`).toBeNull();
    });
  }
});
