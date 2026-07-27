// 10-frontend-spec.md §3.2, §7.4 — <rehearsal-level-meter>. aria-hidden; its information reaches
// screen-reader users via the pre-flight step text and the turn-state announcement, not here.
// Reads level via `peek()` on a rAF loop so it never triggers the effect scheduler (§7.4).
import type { Signal } from '../../store/signal';

export class RehearsalLevelMeter extends HTMLElement {
  private canvas = document.createElement('canvas');
  private raf = 0;
  private source: { level: Signal<number>; clipping: Signal<boolean> } | null = null;

  connectedCallback() {
    this.setAttribute('aria-hidden', 'true');
    this.canvas.width = 240;
    this.canvas.height = 32;
    this.appendChild(this.canvas);
    this.loop();
  }

  disconnectedCallback() {
    cancelAnimationFrame(this.raf);
  }

  /** Bound by the encounter view; never reads the global store directly (§3.1). */
  setSource(source: { level: Signal<number>; clipping: Signal<boolean> } | null) {
    this.source = source;
  }

  private loop = () => {
    const ctx = this.canvas.getContext('2d');
    if (ctx) {
      const level = this.source?.level.peek() ?? 0;
      const clipping = this.source?.clipping.peek() ?? false;
      ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      ctx.fillStyle = clipping ? '#DC2626' : '#0891B2';
      const w = Math.max(2, level * this.canvas.width);
      ctx.fillRect(0, 0, w, this.canvas.height);
    }
    this.raf = requestAnimationFrame(this.loop);
  };
}

customElements.define('rehearsal-level-meter', RehearsalLevelMeter);
