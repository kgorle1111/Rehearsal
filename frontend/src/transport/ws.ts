// 10-frontend-spec.md §6.3-6.4 — SessionSocket: connect, resume-by-seq, gap replay, backoff.
import { signal } from '../store/signal';
import type { Signal } from '../store/signal';
import { isServerEnvelope, type ClientEnvelope, type ServerEnvelope } from './envelope';

export type ConnectionStatus =
  | { kind: 'connecting' }
  | { kind: 'open' }
  | { kind: 'resyncing'; from: number; to: number }
  | { kind: 'reconnecting'; attempt: number; nextMs: number }
  | { kind: 'closed'; reason: string };

const BACKOFF_MS = [250, 500, 1000, 2000, 4000, 8000];

export class SessionSocket {
  readonly status: Signal<ConnectionStatus>;
  private sessionId: string;
  private url: string;
  private ws: WebSocket | null = null;
  private lastSeq = 0;
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private queue: ClientEnvelope[] = [];
  private listeners = new Set<(e: ServerEnvelope) => void>();
  private closedByUser = false;

  constructor(sessionId: string, opts?: { url?: string }) {
    this.sessionId = sessionId;
    this.url = opts?.url ?? `${location.origin.replace(/^http/, 'ws')}/ws/session/${sessionId}`;
    this.status = signal<ConnectionStatus>({ kind: 'connecting' });
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && this.status.peek().kind === 'reconnecting') {
          this.connect();
        }
      });
    }
  }

  connect(): void {
    this.closedByUser = false;
    this.status.set({ kind: 'connecting' });
    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws.addEventListener('open', () => {
      this.attempt = 0;
      this.send({ t: 'hello', d: { last_seq: this.lastSeq || null, client_build: 'dev' } });
      for (const q of this.queue) this.rawSend(q);
      this.queue = [];
    });
    this.ws.addEventListener('message', (ev) => this.handleMessage(ev.data));
    this.ws.addEventListener('close', () => {
      if (!this.closedByUser) this.scheduleReconnect();
    });
    this.ws.addEventListener('error', () => {
      /* the close handler drives reconnection; nothing extra to do here */
    });
  }

  private handleMessage(raw: unknown): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(String(raw));
    } catch {
      return; // §6.2: malformed envelope, logged and dropped, never partially applied
    }
    if (!isServerEnvelope(parsed)) return;
    if (parsed.t === 'gap.begin') {
      const d = parsed.d as { from: number; to: number };
      this.status.set({ kind: 'resyncing', from: d.from, to: d.to });
      return;
    }
    if (parsed.t === 'gap.end') {
      this.status.set({ kind: 'open' });
      return;
    }
    if (parsed.t === 'hello') {
      this.status.set({ kind: 'open' });
    }
    if (parsed.seq > 0) this.lastSeq = Math.max(this.lastSeq, parsed.seq);
    for (const fn of this.listeners) fn(parsed);
  }

  private scheduleReconnect(): void {
    const idx = Math.min(this.attempt, BACKOFF_MS.length - 1);
    const base = BACKOFF_MS[idx] ?? 8000;
    const jitter = base * 0.2 * (Math.random() * 2 - 1);
    const nextMs = Math.max(0, Math.round(base + jitter));
    this.attempt++;
    this.status.set({ kind: 'reconnecting', attempt: this.attempt, nextMs });
    this.timer = setTimeout(() => this.connect(), nextMs);
  }

  send(env: ClientEnvelope): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.queue.push(env);
      return;
    }
    this.rawSend(env);
  }

  private rawSend(env: ClientEnvelope): void {
    this.ws?.send(JSON.stringify(env));
  }

  onEnvelope(fn: (e: ServerEnvelope) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  close(code?: number): void {
    this.closedByUser = true;
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close(code);
    this.status.set({ kind: 'closed', reason: 'client' });
  }
}
