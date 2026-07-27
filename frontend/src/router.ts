// 10-frontend-spec.md — minimal hash router. No client-side route params: each screen that
// needs a session id reads it from module state set by the caller (WS-API is not live yet;
// see BUILD.md WS8 scope note). ponytail: a 20-line hash router covers this app's five stub
// screens plus two real ones — a routing library is unjustified until nested/param routes exist.
export type ViewMount = (container: HTMLElement) => (() => void) | void;

const routes = new Map<string, ViewMount>();
let currentCleanup: (() => void) | void;
let outlet: HTMLElement | null = null;

export function registerRoute(path: string, mount: ViewMount): void {
  routes.set(path, mount);
}

export function initRouter(container: HTMLElement, fallback = '#/practice'): void {
  outlet = container;
  window.addEventListener('hashchange', render);
  if (!location.hash) location.hash = fallback;
  render();
}

function render(): void {
  if (!outlet) return;
  if (currentCleanup) {
    currentCleanup();
    currentCleanup = undefined;
  }
  const hash = location.hash || '#/practice';
  const path = (hash.split('?')[0] ?? hash) as string;
  const mount = routes.get(path) ?? routes.get('#/practice');
  if (!mount) return;
  currentCleanup = mount(outlet) ?? undefined;
}

export function navigate(path: string): void {
  location.hash = path;
}
