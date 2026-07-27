// jsdom does not implement requestAnimationFrame (confirmed: `typeof window.requestAnimationFrame
// === 'undefined'` under jsdom 25). rehearsal-level-meter's render loop calls it unconditionally,
// so every test that mounts the encounter view needs this polyfilled or it throws a
// ReferenceError. setTimeout(...,16) is a fine stand-in — nothing here asserts frame timing.
if (typeof globalThis.requestAnimationFrame === 'undefined') {
  globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
    Number(setTimeout(() => cb(performance.now()), 16))) as typeof requestAnimationFrame;
  globalThis.cancelAnimationFrame = ((id: number) => clearTimeout(id)) as typeof cancelAnimationFrame;
}

// jsdom has no real <canvas> 2D context (would need the native 'canvas' package, which this repo
// doesn't install) and its default stub logs a "not implemented" jsdomError to console.error on
// every call — rehearsal-level-meter's rAF loop calls getContext('2d') every frame, which would
// fail the "0 console errors" fixture-replay assertion for a reason that has nothing to do with
// this app's code. The component already handles `ctx === null` (level-meter.ts:30), so a quiet
// null stub is behaviourally identical to the real jsdom stub, just without the log spam.
if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = (() => null) as typeof HTMLCanvasElement.prototype.getContext;
}
