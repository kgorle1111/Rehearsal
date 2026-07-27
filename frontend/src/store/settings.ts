// 10-frontend-spec.md §5.2 — persisted preferences, key prefix `rehearsal.`.
import { signal } from './signal';
import type { Locale } from '../i18n';

export interface Settings {
  theme: 'light' | 'dark';
  textScale: 1 | 1.15 | 1.3;
  reducedMotion: boolean;
  highContrast: boolean;
  uiLocale: Locale;
  chartMode: 'radar' | 'bars' | 'table';
}

const KEY = 'rehearsal.settings';

function load(): Settings {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...defaults(), ...JSON.parse(raw) };
  } catch {
    /* kn: localStorage unavailable (private mode, SSR-ish test env) — fall through to defaults */
  }
  return defaults();
}

function defaults(): Settings {
  return {
    theme: 'light',
    textScale: 1,
    reducedMotion: false,
    highContrast: false,
    uiLocale: 'en-US',
    chartMode: 'radar',
  };
}

export const settings = signal<Settings>(load());

export function updateSettings(patch: Partial<Settings>): void {
  const next = { ...settings.peek(), ...patch };
  settings.set(next);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* kn: best-effort persistence only */
  }
  document.documentElement.setAttribute('data-theme', next.theme);
  document.documentElement.style.setProperty('--text-scale', String(next.textScale));
  if (next.highContrast) document.documentElement.setAttribute('data-contrast', 'high');
  else document.documentElement.removeAttribute('data-contrast');
}
