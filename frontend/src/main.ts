// 10-frontend-spec.md §2 — app bootstrap. WS-API is not live yet (BUILD.md WS8 scope note), so
// the only routes wired to real data are the ones that don't need a backend session: the
// encounter screen mounts against a fresh local SessionStore, everything else is a stub
// (priority 8 in the WS8 brief). Fixture-driven rendering is exercised directly by the tests,
// not through this router.
import { t } from './i18n';
import { updateSettings } from './store/settings';
import { createSessionStore } from './store/session';
import { registerRoute, initRouter } from './router';
import { mountEncounterView } from './views/encounter-view';
import { mountStubView } from './views/stub-view';

function renderShell(): HTMLElement {
  const app = document.getElementById('app');
  if (!app) throw new Error('#app not found');
  app.innerHTML = '';

  const nav = document.createElement('nav');
  nav.setAttribute('aria-label', t('app.title'));
  const navItems: Array<[string, string]> = [
    ['#/practice', 'nav.practice'],
    ['#/progress', 'nav.progress'],
    ['#/library', 'nav.library'],
    ['#/review', 'nav.review'],
    ['#/settings', 'nav.settings'],
  ];
  for (const [href, key] of navItems) {
    const a = document.createElement('a');
    a.href = href;
    a.textContent = t(key);
    nav.appendChild(a);
  }

  const main = document.createElement('main');
  main.id = 'router-outlet';
  app.append(nav, main);
  return main;
}

export function bootstrap(): void {
  updateSettings({}); // apply persisted theme/text-scale/contrast to <html> before first paint
  const outlet = renderShell();

  registerRoute('#/practice', mountStubView('nav.practice'));
  registerRoute('#/progress', mountStubView('nav.progress'));
  registerRoute('#/library', mountStubView('nav.library'));
  registerRoute('#/review', mountStubView('nav.review'));
  registerRoute('#/settings', mountStubView('nav.settings'));
  registerRoute('#/encounter', (c) => mountEncounterView(c, createSessionStore('local')));

  initRouter(outlet);
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }
}
