// BUILD.md WS8 DoD, priority 6 — keyboard-only traversal of the report view, no mouse.
// Uses native focus() + click()-as-Enter-activation (jsdom has no built-in "press Enter on a
// focused button" behaviour the way a real browser does, so `.click()` stands in for it — see
// https://github.com/jsdom/jsdom/issues/1026). <details>/<summary> disclosure is tested via its
// real toggle behaviour, which needs no simulated key at all: it's a native control.
import { describe, it, expect } from 'vitest';
import { mountReportView } from '../src/views/report-view';
import type { SessionReport } from '../src/types/api';
import reportFixture from './fixtures/session-report.json';

function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), summary, [tabindex]:not([tabindex="-1"])',
    ),
  );
}

describe('keyboard-only traversal — report view', () => {
  it('reaches every interactive control by focus and activates them without a mouse', () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    mountReportView(container, reportFixture as unknown as SessionReport);

    const focusable = focusableElements(container);
    // header buttons (3 chart-mode toggles + 3 export actions) + one <summary> per turn (2 turns)
    expect(focusable.length).toBeGreaterThanOrEqual(8);

    for (const el of focusable) {
      el.focus();
      expect(document.activeElement).toBe(el);
    }

    const barsBtn = container.querySelector<HTMLButtonElement>('button[data-mode="bars"]');
    expect(barsBtn).toBeTruthy();
    expect(barsBtn!.getAttribute('aria-pressed')).toBe('false');
    barsBtn!.focus();
    barsBtn!.click(); // the DOM-level effect of pressing Enter/Space on a focused button
    expect(barsBtn!.getAttribute('aria-pressed')).toBe('true');
    expect(container.querySelectorAll('rect').length).toBeGreaterThan(0);

    const summary = container.querySelector('summary');
    expect(summary).toBeTruthy();
    const details = summary!.parentElement as HTMLDetailsElement;
    expect(details.open).toBe(false);
    summary!.focus();
    summary!.click(); // native <details> toggle behaviour, keyboard-operable with no script
    expect(details.open).toBe(true);

    container.remove();
  });
});
