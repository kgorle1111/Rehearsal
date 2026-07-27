// 10-frontend-spec.md §5.1 — the ~120-line signal store. Pull-based dependency tracking;
// effects are scheduled on a microtask so a burst of socket events (§5.1: "six envelopes in
// under 20ms") produces one DOM flush, not one per event.

type Effect = { run(): void; deps: Set<Set<Effect>> };

let activeEffect: Effect | null = null;
const pendingEffects = new Set<Effect>();
let flushScheduled = false;
let batchDepth = 0;

function scheduleFlush(): void {
  if (flushScheduled || batchDepth > 0) return;
  flushScheduled = true;
  queueMicrotask(flush);
}

function flush(): void {
  flushScheduled = false;
  const toRun = Array.from(pendingEffects);
  pendingEffects.clear();
  for (const e of toRun) e.run();
}

export interface Signal<T> {
  (): T;
  set(v: T): void;
  peek(): T;
}

export interface Computed<T> {
  (): T;
  peek(): T;
}

export function signal<T>(initial: T): Signal<T> {
  let value = initial;
  const subscribers = new Set<Effect>();

  const read = (() => {
    if (activeEffect) {
      subscribers.add(activeEffect);
      activeEffect.deps.add(subscribers);
    }
    return value;
  }) as Signal<T>;

  read.peek = () => value;
  read.set = (v: T) => {
    if (Object.is(v, value)) return;
    value = v;
    for (const e of subscribers) pendingEffects.add(e);
    scheduleFlush();
  };

  return read;
}

export function computed<T>(fn: () => T): Computed<T> {
  let value: T;
  let stale = true;
  const subscribers = new Set<Effect>();

  const recompute: Effect = {
    deps: new Set(),
    run() {
      stale = true;
      for (const e of subscribers) pendingEffects.add(e);
      if (subscribers.size > 0) scheduleFlush();
    },
  };

  const read = (() => {
    if (stale) {
      for (const d of recompute.deps) d.delete(recompute);
      recompute.deps.clear();
      const prev = activeEffect;
      activeEffect = recompute;
      try {
        value = fn();
      } finally {
        activeEffect = prev;
      }
      stale = false;
    }
    if (activeEffect) {
      subscribers.add(activeEffect);
      activeEffect.deps.add(subscribers);
    }
    return value;
  }) as Computed<T>;

  read.peek = () => read();

  return read;
}

export function effect(fn: () => void | (() => void)): () => void {
  let cleanup: void | (() => void);
  const e: Effect = {
    deps: new Set(),
    run() {
      for (const d of e.deps) d.delete(e);
      e.deps.clear();
      if (cleanup) cleanup();
      const prev = activeEffect;
      activeEffect = e;
      try {
        cleanup = fn();
      } finally {
        activeEffect = prev;
      }
    },
  };
  e.run();
  return () => {
    for (const d of e.deps) d.delete(e);
    e.deps.clear();
    if (cleanup) cleanup();
  };
}

export function batch(fn: () => void): void {
  batchDepth++;
  try {
    fn();
  } finally {
    batchDepth--;
    if (batchDepth === 0) scheduleFlush();
  }
}
