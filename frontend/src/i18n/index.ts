// 10-frontend-spec.md §11 — ICU MessageFormat via intl-messageformat. UI language and
// encounter languages are independent axes (§11.1): `locale` here is the UI locale only.
import IntlMessageFormat from 'intl-messageformat';
import { signal } from '../store/signal';
import enUS from './catalog/en-US.json';
import esMX from './catalog/es-MX.json';

export type Locale = 'en-US' | 'es-MX';

const catalogs: Record<Locale, Record<string, string>> = {
  'en-US': enUS,
  'es-MX': esMX,
};

// kn: compiled once per key per locale, per §11.2 — recompiling ICU patterns in a render loop
// is a real cost in the transcript.
const compiledCache = new Map<string, IntlMessageFormat>();

export const locale = signal<Locale>('en-US');

export async function setLocale(l: Locale): Promise<void> {
  locale.set(l);
  if (typeof document !== 'undefined') document.documentElement.lang = l;
}

export function t(key: string, vars?: Record<string, unknown>): string {
  const l = locale();
  const cacheKey = `${l}:${key}`;
  let msg = compiledCache.get(cacheKey);
  if (!msg) {
    const pattern = catalogs[l][key];
    if (pattern === undefined) {
      console.error(`i18n: missing key "${key}" for locale "${l}"`);
      return key;
    }
    msg = new IntlMessageFormat(pattern, l);
    compiledCache.set(cacheKey, msg);
  }
  return String(msg.format(vars as Record<string, string | number>));
}

export function formatNumber(n: number, opts?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(locale(), opts).format(n);
}

export function formatPercent(n: number): string {
  return new Intl.NumberFormat(locale(), { style: 'percent', maximumFractionDigits: 0 }).format(n);
}

export function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

/** Exposed for the i18n-leak test: the full key set for a locale. */
export function keysFor(l: Locale): string[] {
  return Object.keys(catalogs[l]);
}
