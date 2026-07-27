# 10 — Frontend Specification

The implementation contract for the interface designed in `docs/09-ui-ux.md`. That document defines *what the interface is and why*; this one defines *how it is built* — modules, tokens, state contracts, transport, audio, component states, accessibility mechanics, i18n architecture, performance budgets and failure behaviour.

**Scope boundary.** This document does not redesign anything. Where a visual or interaction decision is needed, it is taken from `docs/09-ui-ux.md` and cited by section number. Where this document introduces something that document does not cover, it is marked **[proposed]** or **[open]** and named as an addition.

**Status legend used throughout:** **[decided]** — settled, build to it. **[proposed]** — the recommended answer, not yet ratified. **[open]** — genuinely unresolved, with the resolution path stated.

---

## 1. Constraints that drive every choice here

Five properties of this product, not general web preferences, determine the architecture below.

| Constraint | Source | Consequence for the frontend |
|---|---|---|
| The frontend is a **view over a server-owned event log** | `docs/03-system-architecture.md` §10.1, §13.3 | No client-authoritative session state. Ever. The client folds events; it never computes what a turn is. A dropped socket makes the UI stale, never wrong. |
| **Ships from `127.0.0.1`**, single user, single session | `docs/03-system-architecture.md` §13.2 | No CDN, no code splitting for network reasons, no auth token dance in the client, no CORS. Cold load is disk-speed. Budgets are about *main-thread work*, not bytes over a wire. |
| The **encounter is a real-time attention-critical surface** | `docs/09-ui-ux.md` §1, §5.3 | Rendering during a live turn must not cause layout thrash, GC spikes, or long tasks. The encounter view has a hard frame budget separate from the rest of the app. |
| The UI is **bilingual in two independent dimensions** | `docs/09-ui-ux.md` §2.2, §5.8 | UI language and encounter languages are separate axes. `lang` is a per-node property, not a document property. |
| **Assessment output is a record about a person** | `docs/09-ui-ux.md` §5.5 §7 | Degradation, partial verdicts and unscored turns must be structurally impossible to render as "clean". The renderer refuses to display absence as success. |

---

## 2. Stack and build

### 2.1 Framework decision [decided]

**No UI framework.** The frontend is TypeScript 5.x compiled by Vite 5, using native Custom Elements + a ~120-line signal store. Rationale, in the same terms the backend uses to reject agent frameworks:

- The load-bearing complexity is the **event fold** and the **audio path**, neither of which a component framework helps with. React would add a reconciler between the event stream and the DOM at exactly the point where we need to reason about frame timing during a live turn.
- Dependency surface on a locally-served, single-user tool has no upside and a real audit cost (`docs/12-security-privacy.md`).
- Everything the encounter screen needs — a level meter, four turn states, two scrollbacks — is less code hand-written than the glue to make a framework do it well.

**When to revisit:** if the trainer review queue and progress dashboard together exceed ~4,000 lines of view code, or if two engineers start diverging on state-update patterns, the framework question is worth reopening. That is the trigger; nothing before it is.

### 2.2 Dependencies [decided]

| Package | Purpose | Why not hand-rolled / why not something bigger |
|---|---|---|
| `vite` (dev + build) | Bundling, TS transform, dev server | Build tooling only; zero runtime footprint |
| `typescript` | Types | Non-negotiable for a state contract this shaped |
| `@formatjs/intl-messageformat` (~9 kB gz) | ICU MessageFormat: plurals, gendered strings, number/date interpolation | Spanish plural and gender rules are not a `${}` template. Getting this wrong in front of language professionals is the one class of bug the product cannot afford (`docs/09-ui-ux.md` §7) |
| `uplot` (~18 kB gz) | Line/sparkline charts in Progress | Canvas-based, no virtual DOM, renders 5k points without dropping frames. Chart.js and D3 are both larger for less of what we need |
| `vitest` + `@vitest/browser` (dev) | Unit and DOM tests | Shares Vite's transform pipeline; no second config |
| `axe-core` (dev only) | Automated a11y assertions in tests | Catches the mechanical half of WCAG; the rest is manual (§10.8) |

**Explicitly rejected:** any component library (imposes its own token system and a11y assumptions), any state-management library (the store is smaller than its README), any date library (`Intl.DateTimeFormat` covers it), any icon font (inline SVG sprite, §4.6).

Bar chart, radar chart and horizontal-bar chart are **hand-drawn SVG**, not `uplot` — they are static-per-render, need per-mark `aria` and pattern fills for the never-colour-alone rule (`docs/09-ui-ux.md` §2.1), and SVG gives all three for free.

### 2.3 Directory layout

```
frontend/
├── index.html                       # single entry; no other HTML files
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── main.ts                      # bootstrap: router, store, transport, i18n
│   ├── router.ts                    # hash router, 6 routes, ~90 lines
│   ├── store/
│   │   ├── signal.ts                # signal(), computed(), effect(), batch()
│   │   ├── session.ts               # SessionView fold + live subscriptions
│   │   ├── fold.ts                  # applyEvent(view, envelope) -> SessionView
│   │   ├── settings.ts              # persisted prefs (localStorage)
│   │   └── selectors.ts             # derived read models for views
│   ├── transport/
│   │   ├── ws.ts                    # SessionSocket: connect, resume-by-seq, backoff
│   │   ├── http.ts                  # typed fetch wrapper over /api/*
│   │   └── envelope.ts              # ServerEnvelope / ClientEnvelope types + guards
│   ├── audio/
│   │   ├── capture.ts               # getUserMedia, device enumeration, graph setup
│   │   ├── pcm-worklet.ts           # AudioWorkletProcessor: downsample + frame
│   │   ├── level.ts                 # RMS/peak metering off the worklet message port
│   │   └── headphone-check.ts       # tone playback + confirmation gate
│   ├── i18n/
│   │   ├── index.ts                 # loader, formatter cache, t()
│   │   └── catalog/
│   │       ├── en-US.json
│   │       └── es-MX.json
│   ├── components/                  # custom elements, one file each (§3.2)
│   │   ├── encounter/
│   │   ├── report/
│   │   ├── progress/
│   │   ├── review/
│   │   └── common/
│   ├── views/                       # one per route; composes components
│   │   ├── practice-view.ts  preflight-view.ts  encounter-view.ts
│   │   ├── report-view.ts    progress-view.ts   library-view.ts
│   │   ├── review-view.ts    settings-view.ts
│   ├── styles/
│   │   ├── tokens.css               # §4 — the single source of design truth
│   │   ├── base.css                 # reset, type, focus, reduced-motion
│   │   └── layout.css               # grid primitives only
│   └── types/
│       └── api.ts                   # generated from backend Pydantic models (§5.5)
├── test/
└── dist/                            # build output, mounted by rehearsal-api
```

`frontend/dist` is served by `rehearsal-api` as a static mount (`docs/03-system-architecture.md` §13.2). There is no separate frontend server in production; `vite dev` proxies `/api` and `/ws` to `127.0.0.1:8420` in development only.

---

## 3. Component architecture

### 3.1 The three tiers

| Tier | What it is | Rules |
|---|---|---|
| **Views** (`src/views/`) | One per route. Owns route-level data loading and the page's landmark structure. | May read the store directly. May call HTTP. Never touches the WebSocket or audio APIs. |
| **Components** (`src/components/`) | Custom elements, `rehearsal-*` prefix. | **Never read the global store.** Data in via properties, events out via `CustomEvent`. This is what makes them testable in isolation and is enforced by lint rule `no-restricted-imports` on `store/` inside `components/`. |
| **Services** (`store/`, `transport/`, `audio/`, `i18n/`) | Singletons created in `main.ts`. | No DOM access. Anything that touches the DOM belongs in a component. |

Custom elements are used **without Shadow DOM** [decided]. Shadow roots would isolate the token layer per component and complicate the `lang`-attribute inheritance that the bilingual screen-reader requirement depends on (`docs/09-ui-ux.md` §6). Styles are scoped by a single class prefix per component instead; the trade is real and accepted.

### 3.2 Component inventory → implementation

Every component in the `docs/09-ui-ux.md` §9 inventory, with its element name, inputs and events. Additions beyond that inventory are marked **+**.

| Element | Properties (in) | Events (out) | Notes |
|---|---|---|---|
| `<rehearsal-turn-state>` | `state: TurnState`, `turnIndex: number`, `reducedMotion: boolean` | — | Owns the only animation in the encounter. Writes the live region (§10.3) |
| `<rehearsal-speaker-panel>` | `speaker`, `lang`, `active: boolean`, `utterances: Utterance[]` | `panel-scrolled` | Two instances, mirrored. Hosts a `<rehearsal-transcript>` |
| `<rehearsal-level-meter>` | `level: number` (0–1), `clipping: boolean`, `mode: 'bar'\|'wave'` | — | Reads from an `AudioLevelSource` handle, never from the store. `rAF`-driven, canvas |
| `<rehearsal-directional-cue>` | `direction: 'en->es'\|'es->en'` | — | Largest text on the encounter screen. Text, not icon (`docs/09-ui-ux.md` §5.3) |
| `<rehearsal-transcript>` | `items: TranscriptItem[]`, `follow: boolean`, `virtualise: boolean` | `follow-changed`, `item-focused` | Windowed list (§11.4) |
| `<rehearsal-source-diff>` | `source: TextBlock`, `rendering: TextBlock`, `findings: Finding[]` | `span-activated` | The core comparison component. Renders span marks by char offset (§3.4) |
| `<rehearsal-finding-card>` | `finding: Finding`, `overridable: boolean`, `override?: Override` | `override-requested` | Icon + label + colour, all three always (`docs/09-ui-ux.md` §2.1) |
| `<rehearsal-competency-chart>` | `dimensions: SkillScore[]`, `mode: 'radar'\|'bars'\|'table'` | `mode-changed` | Radar and bars are the same data, two renderers; table is the third mandatory view |
| `<rehearsal-trend-chart>` | `series: Series[]`, `mode: 'chart'\|'table'` | `mode-changed`, `point-focused` | `uplot` instance, destroyed on disconnect |
| `<rehearsal-scenario-card>` | `scenario: ScenarioSummary`, `recommendation?: Recommendation` | `scenario-selected` | Never renders scenario dialogue (`docs/09-ui-ux.md` §5.1) |
| `<rehearsal-preflight-step>` | `step: PreflightStep`, `status: StepStatus` | `retry-requested`, `step-passed` | Failure text carries the actionable remedy string, never a generic error |
| `<rehearsal-mode-badge>` | `mode: 'practice'\|'assessment'` | — | Persistent in the encounter header in assessment mode |
| `<rehearsal-coach-card>` | `interjection: Coach`, `capped: boolean` | `coach-dismissed` | Enters only between turns; see §3.5 |
| `<rehearsal-review-item>` | `item: ReviewQueueItem` | `item-opened` | Trainer queue row |
| `<rehearsal-confidence-disclosure>` | `metrics: GraderAgreement` | — | Non-collapsible by construction: no `open`/`aria-expanded` API exists on it |
| **+** `<rehearsal-degrade-banner>` | `level: DegradeLevel`, `reason: string` | — | Renders the ladder state (`docs/03-system-architecture.md` §14). Required: nothing degrades silently |
| **+** `<rehearsal-device-picker>` | `devices: MediaDeviceInfo[]`, `selectedId: string` | `device-changed` | Pre-flight and Settings |
| **+** `<rehearsal-connection-status>` | `status: ConnectionStatus`, `staleMs: number` | `reconnect-requested` | Socket health; see §6.5 |
| **+** `<rehearsal-empty-state>` | `title`, `body`, `action?` | `action-invoked` | One implementation so every empty state is meaningful, not blank |

### 3.3 Component tree per screen

Only the structurally interesting screens are given in full; the rest follow the same shape.

**Encounter** (`/#/session/{id}`) — full-viewport, no app chrome (`docs/09-ui-ux.md` §3):

```
<encounter-view>                          role=main, aria-label="Encounter"
├── <header class="encounter-bar">
│   ├── <button data-act="exit">                       ← Esc
│   ├── <span class="scenario-title">
│   ├── <rehearsal-mode-badge>
│   ├── <span class="turn-counter" aria-hidden="true">   (announced via live region instead)
│   ├── <time class="elapsed" aria-hidden="true">
│   └── <rehearsal-connection-status>
├── <rehearsal-degrade-banner>            (present only when level > L0)
├── <div class="triad-grid">              CSS grid: 1fr 1.2fr 1fr
│   ├── <rehearsal-speaker-panel role="clinician" lang="en">
│   │   └── <rehearsal-transcript lang="en">
│   ├── <section class="trainee-column">
│   │   ├── <rehearsal-turn-state>
│   │   ├── <rehearsal-directional-cue>
│   │   ├── <rehearsal-level-meter>
│   │   ├── <rehearsal-coach-card>        (practice mode, between turns only)
│   │   └── <rehearsal-transcript class="renderings">
│   └── <rehearsal-speaker-panel role="patient" lang="es">
│       └── <rehearsal-transcript lang="es">
├── <footer class="encounter-actions">
│   ├── <button data-act="repeat">        ← R
│   ├── <button data-act="notes">         ← N   toggles <rehearsal-notes-pad>
│   └── <button data-act="end">
├── <div id="turn-announcer" aria-live="polite" aria-atomic="true" class="sr-only">
└── <div id="status-announcer" aria-live="polite" class="sr-only">
```

Two live regions, not one, and the reason is mechanical: turn-change announcements and status announcements (degradation, connection, coach availability) can be queued simultaneously, and a single region would have the second overwrite the first before it is spoken. The turn announcer is the one the trainee must never miss.

**Session report** (`/#/report/{id}`):

```
<report-view>                             role=main
├── <header>  scenario · mode · duration · turn count · session id
├── <section class="at-a-glance">         clean vs findings, critical count, one-line summary
├── <rehearsal-competency-chart mode="radar|bars|table">
├── <section class="turn-by-turn">
│   └── <details> per turn  (collapsible, filter by severity + error kind)
│       └── <rehearsal-source-diff>
│           └── <rehearsal-finding-card> ×n
├── <section class="patterns">
├── <section class="next">
├── <rehearsal-confidence-disclosure>     always rendered, never collapsible
└── <footer class="export">               PDF · JSON · Delete
```

**Pre-flight** (`/#/preflight/{id}`) — an ordered, gated list; step *n+1* is `disabled` until step *n* reports `passed`:

```
<preflight-view>
├── <ol class="preflight-steps">
│   ├── <rehearsal-preflight-step step="microphone">
│   │   ├── <rehearsal-device-picker>
│   │   ├── <rehearsal-level-meter mode="bar">
│   │   └── 3-second confirmation capture
│   ├── <rehearsal-preflight-step step="headphones">   ← tone + explicit confirm (§7.5)
│   ├── <rehearsal-preflight-step step="models">       ← reads host readiness from /api
│   └── <rehearsal-preflight-step step="confirm">      ← mode + scenario summary
└── <button data-act="begin" disabled-until-all-passed>
```

### 3.4 `<rehearsal-source-diff>` — the span-marking contract

This is the component most likely to be implemented wrongly, so its contract is explicit.

Findings carry `span: (start, end) | null` into the **rendering** and `source_span: (start, end) | null` into the **source** (`docs/03-system-architecture.md` §7). Both are **character offsets into the canonical UTF-8-decoded string as delivered by the API**.

```ts
interface TextBlock { text: string; lang: 'en' | 'es'; }
interface SpanMark  { start: number; end: number; findingId: number; severity: Severity; kind: ErrorKind; }
```

Implementation rules:

1. Offsets are applied over the string's **code points**, iterated with `Array.from()` or a `Intl.Segmenter('…', {granularity:'grapheme'})` walk — never `String.prototype.slice` on UTF-16 indices. Spanish text is BMP-safe, but emoji or combining marks pasted into a typed rendering (transcript-only mode) would silently shift every subsequent offset. `Intl.Segmenter` is available in all target browsers (§11.1). **[decided]**
2. Overlapping spans are resolved by splitting at every boundary and rendering the innermost segment with the **highest severity** present; the segment's `aria-describedby` lists every overlapping finding. Dropping an overlap would hide a finding.
3. An omission has `span === null` — there is nothing in the rendering to mark. It renders as an **insertion caret** at the source-aligned position with the source span marked, plus the finding card. It must never render as "no mark", which reads as "no error".
4. Each mark is `<mark class="span span--critical" tabindex="0" aria-describedby="finding-{id}">` — keyboard reachable, since `docs/09-ui-ux.md` §6 requires every function reachable without a mouse.
5. Three channels always: `text-decoration: underline`, background tint, and a leading icon anchor. Colour alone is prohibited.
6. **Span-offset drift is a data bug, not a rendering bug.** If `end > text.length` for any mark, the component renders the unmarked text plus a visible `SPAN_OUT_OF_RANGE` notice and reports `console.error` with the `verdict_key`. It does not clamp silently — a clamped span mis-attributes an error to the wrong words on a record about a person.

### 3.5 Coach card timing

`coach.emitted` may arrive from the socket at any moment, including mid-utterance. The component does **not** render on arrival. `store/session.ts` buffers coach interjections in `pendingCoach` and flushes them only on the `turn.closed` → `turn.opened` boundary, and only in practice mode. If a second interjection arrives while one is pending, the older is dropped and counted (the cap in `docs/09-ui-ux.md` §5.3 is a UI-side cap over the backend's own `coach.suppressed` rule). A `coach.emitted` that arrives after `encounter.ended` is discarded.

---

## 4. Design-token layer

`src/styles/tokens.css` is the **single source of visual truth**. No component file may contain a literal colour, duration, radius or spacing value. Enforced by a stylelint rule (`declaration-property-value-disallowed-list` on hex literals and `ms`/`px` in the disallowed properties).

### 4.1 Colour tokens

Values from `docs/09-ui-ux.md` §2.1. Dark mode is a separate authored set, never a filter or inversion.

```css
:root {
  color-scheme: light dark;

  /* ── colour ─────────────────────────────────────────────── */
  --color-primary:          #0891B2;
  --color-on-primary:       #FFFFFF;
  --color-secondary:        #22D3EE;
  --color-accent:           #059669;
  --color-background:       #ECFEFF;
  --color-surface:          #FFFFFF;
  --color-foreground:       #164E63;
  --color-muted:            #E8F1F6;
  --color-muted-foreground: #64748B;
  --color-border:           #A5F3FC;
  --color-destructive:      #DC2626;
  --color-warning:          #D97706;
  --color-ring:             #0891B2;

  /* derived, low-alpha span tints — authored, not computed at runtime */
  --tint-critical:     #FDECEC;
  --tint-non-critical: #FEF4E6;
  --tint-clean:        #E8F7F1;
}

[data-theme="dark"] {
  --color-primary:          #22D3EE;
  --color-on-primary:       #083344;
  --color-secondary:        #67E8F9;
  --color-accent:           #34D399;
  --color-background:       #0B1418;
  --color-surface:          #132025;
  --color-foreground:       #E6F6FA;
  --color-muted:            #1B2C33;
  --color-muted-foreground: #94A9B4;
  --color-border:           #25404A;
  --color-destructive:      #F87171;
  --color-warning:          #FBBF24;
  --color-ring:             #22D3EE;

  --tint-critical:     #2A1618;
  --tint-non-critical: #2A2113;
  --tint-clean:        #12251E;
}
```

Theme resolution order: `localStorage['rehearsal.theme']` → `prefers-color-scheme` → light. `data-theme` is written on `<html>` **before first paint** by a 6-line inline script in `index.html`, to avoid a light flash on a dark-mode machine.

### 4.2 The full token table

| Token | Light | Dark | Applies to |
|---|---|---|---|
| **Type family** | | | |
| `--font-heading` | `Figtree, system-ui, sans-serif` | same | h1–h4, section titles |
| `--font-body` | `"Noto Sans", system-ui, sans-serif` | same | all body, **all encounter text** |
| `--font-mono` | `ui-monospace, "SF Mono", monospace` | same | session ids, hashes, diagnostics |
| **Type scale** (`docs/09-ui-ux.md` §2.2) | | | |
| `--text-xs` | `0.75rem` / 12px | same | table meta, chart axis labels |
| `--text-sm` | `0.875rem` / 14px | same | secondary labels, captions |
| `--text-base` | `1rem` / 16px | same | body minimum, never smaller |
| `--text-lg` | `1.125rem` / 18px | same | transcript text |
| `--text-xl` | `1.25rem` / 20px | same | card titles |
| `--text-2xl` | `1.5rem` / 24px | same | section headings |
| `--text-3xl` | `2rem` / 32px | same | page titles |
| `--text-4xl` | `2.5rem` / 40px | same | directional cue, at-a-glance numbers |
| `--leading-body` | `1.5` | same | body |
| `--leading-heading` | `1.25` | same | headings |
| `--measure-read` | `70ch` | same | prose surfaces |
| `--measure-transcript` | `55ch` | same | transcript columns |
| `--numeric` | `tabular-nums` | same | scores, tables, timers |
| **Spacing** (8pt rhythm) | | | |
| `--space-1` | `4px` | same | icon gaps |
| `--space-2` | `8px` | same | tight stacks, min target separation |
| `--space-3` | `12px` | same | control padding |
| `--space-4` | `16px` | same | default gap |
| `--space-6` | `24px` | same | card padding |
| `--space-8` | `32px` | same | section gap |
| `--space-12` | `48px` | same | major section gap |
| `--space-16` | `64px` | same | page gutters ≥1440px |
| **Radius** | | | |
| `--radius-control` | `6px` | same | buttons, inputs, pickers |
| `--radius-card` | `10px` | same | cards, panels |
| `--radius-modal` | `16px` | same | modals, overlays |
| `--radius-pill` | `9999px` | same | badges, mode badge, filters |
| **Elevation** (three levels only) | | | |
| `--elev-flat` | `none` | `none` | in-flow surfaces |
| `--elev-card` | `0 1px 3px rgba(22,78,99,.08)` | `0 1px 3px rgba(0,0,0,.45)` | cards, speaker panels |
| `--elev-overlay` | `0 8px 24px rgba(22,78,99,.16)` | `0 8px 24px rgba(0,0,0,.60)` | modals, popovers, coach card |
| **Motion** | | | |
| `--motion-micro` | `150ms` | same | hover, press, focus |
| `--motion-state` | `200ms` | same | turn-state change, panel raise |
| `--motion-panel` | `300ms` | same | panel/route transitions |
| `--ease-enter` | `cubic-bezier(0, 0, .2, 1)` | same | entering (ease-out) |
| `--ease-exit` | `cubic-bezier(.4, 0, 1, 1)` | same | exiting (ease-in) |
| `--motion-exit-ratio` | `0.7` | same | exits are 70% of enter duration |
| **Focus** | | | |
| `--focus-width` | `2px` | same | ring thickness |
| `--focus-offset` | `2px` | same | ring offset |
| `--focus-color` | `var(--color-ring)` | `var(--color-ring)` | never `none`, ever |
| **Targets** | | | |
| `--target-min` | `44px` | same | every interactive element |
| `--target-gap` | `8px` | same | minimum separation |
| **Layout** | | | |
| `--bp-sm` / `--bp-md` / `--bp-lg` / `--bp-xl` | `768 / 1024 / 1440px` | same | breakpoints (`docs/09-ui-ux.md` §8) |
| `--sidebar-w` | `248px` | same | persistent nav ≥1024px |
| `--z-content` / `--z-sticky` / `--z-overlay` / `--z-modal` / `--z-toast` | `0 / 10 / 100 / 200 / 300` | same | the entire z-index vocabulary |

Media-query breakpoints cannot consume custom properties; `--bp-*` exist for JS (`matchMedia`) and documentation, and the CSS values are duplicated in `layout.css` with a comment pointing here. That duplication is deliberate and is the only one permitted.

### 4.3 Reduced motion

```css
@media (prefers-reduced-motion: reduce) {
  :root { --motion-micro: 0ms; --motion-state: 0ms; --motion-panel: 0ms; }
  *, *::before, *::after {
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
}
```

Zeroing the tokens covers CSS. The **waveform** is canvas-driven and therefore not covered: `<rehearsal-level-meter>` reads `matchMedia('(prefers-reduced-motion: reduce)')` and switches to `mode="bar"` — a static level bar that updates at 10 Hz instead of a 60 Hz waveform (`docs/09-ui-ux.md` §2.3). The bar still moves, because it conveys *live microphone state* and removing it would remove information, not decoration. That distinction — motion that decorates is removed, motion that informs is reduced — is the rule for every future case.

Settings exposes an explicit reduced-motion override that wins over the OS query, because the OS setting is machine-wide and a trainee may want it only here.

### 4.4 Text scale

Settings' text-scale control sets `--text-scale` (1.0 / 1.15 / 1.3) on `<html>`; every `--text-*` token is `calc(<base> * var(--text-scale, 1))`. Layouts are tested at 1.3 with Spanish strings, which is the worst case for overflow (`docs/09-ui-ux.md` §2.2 expansion note).

### 4.5 High contrast

`[data-contrast="high"]` overrides `--color-foreground`, `--color-border`, `--color-muted-foreground` and the tints to a set independently tested at ≥7:1. It is an authored token set, not a filter.

### 4.6 Icons

One inline SVG sprite (`src/components/common/sprite.ts`, ~14 symbols, ~4 kB) injected once at boot. Each icon usage is `<svg aria-hidden="true"><use href="#icon-alert-octagon"/></svg>` with an adjacent text label — never a bare icon carrying meaning.

---

## 5. State management and the session contract

### 5.1 The signal store

```ts
// src/store/signal.ts
type Signal<T>   = { (): T; set(v: T): void; peek(): T };
type Computed<T> = { (): T; peek(): T };

export function signal<T>(initial: T): Signal<T>;
export function computed<T>(fn: () => T): Computed<T>;
export function effect(fn: () => void | (() => void)): () => void;  // returns dispose
export function batch(fn: () => void): void;
```

Pull-based with dependency tracking; `effect` re-runs on change and is scheduled on a microtask so a batch of socket events produces **one** DOM update, not one per event. This scheduling property is the reason a store exists at all: a busy turn can deliver six envelopes in under 20 ms.

### 5.2 State ownership

| State | Owner | Lifetime | Persistence |
|---|---|---|---|
| `SessionView` (turns, state, findings, degrade level) | `store/session.ts`, folded from the event stream | Session | **Server.** Client copy is disposable |
| Route + params | `router.ts` | Navigation | URL hash |
| UI-local (scroll follow, filters, expanded turns, chart mode) | Component instances | Component | None (except chart mode, §5.4) |
| Settings (theme, text scale, reduced motion, UI locale, device ids, mode default) | `store/settings.ts` | Persistent | `localStorage`, key prefix `rehearsal.` |
| Notes pad content | Component + debounced `POST /api/sessions/{id}/notes` | Session | Server; never scored (`docs/09-ui-ux.md` §5.3) |
| Audio device permission + stream | `audio/capture.ts` | Session | Device *id* persisted; stream never |

**There is no client-side session state that is not derivable from the event log.** This is the single most important rule in this document. If a feature seems to need one, the event kind is missing from `docs/03-system-architecture.md` §10.2 and that is where it gets added.

### 5.3 The fold

```ts
// src/store/fold.ts
export function applyEvent(view: SessionView, env: ServerEnvelope): SessionView;
export function foldAll(events: ServerEnvelope[]): SessionView;
```

`applyEvent` is **pure**, has no imports outside `types/`, and mirrors `fold()` in `src/rehearsal/orchestrator/resume.py` (`docs/03-system-architecture.md` §8.3) for the subset of fields the UI renders. Two independent implementations of a fold is a real risk of divergence; the mitigation is a shared fixture: `test/fixtures/fold-cases.json` contains recorded event sequences with expected folded output, and the same file is asserted against by `tests/test_fold_parity.py` on the Python side. A field the UI needs that the Python fold does not produce is a spec change, not a client-side patch. **[decided]**

Unknown event kinds are **ignored but counted** (`view.unknownKinds`), never thrown on. A backend that ships a new event kind must not break a running UI, and an unexplained count in diagnostics is how we find out we are behind.

```ts
interface SessionView {
  sessionId: string;
  state: SessionState;              // docs/03-system-architecture.md §8.1
  mode: 'practice' | 'assessment';
  scenario: { id: string; title: string; setting: string };
  turnIndex: number;
  turns: TurnView[];
  turnState: TurnState;             // derived: see §5.4
  degrade: { level: 0|1|2|3|4|5; reason: string | null };
  pendingCoach: Coach | null;
  lastSeq: number;
  textMode: boolean;                // L4 degradation or transcript-only mode
  unknownKinds: Record<string, number>;
}

interface TurnView {
  index: number;
  speaker: 'clinician' | 'patient';
  direction: 'en->es' | 'es->en';
  source: TextBlock | null;         // present from source.emitted
  rendering: TextBlock | null;      // present from rendering.emitted — never before
  partial: boolean;
  verdict: VerdictView | null;      // present from verdict.merged; null = NOT YET SCORED
  audioSha: string | null;
}

interface VerdictView {
  status: 'complete' | 'partial' | 'grader_unavailable';
  nCritical: number;
  nNonCritical: number;
  findings: Finding[];
  overrides: Override[];
}
```

`verdict: null` and `verdict.status !== 'complete'` are **different renderings and both are mandatory**. `null` → "Not yet scored". `partial` / `grader_unavailable` → "Critical checks only — semantic categories not assessed". Neither may render as a clean turn. This is the frontend's half of `docs/03-system-architecture.md` §14: *semantic categories are reported as not assessed, never as no error found*. A unit test asserts that no code path produces the clean-turn confirmation when `verdict` is `null` or `status !== 'complete'`.

### 5.4 Derived read models

```ts
// src/store/selectors.ts
export const turnState:      Computed<TurnState>;        // 'clinician'|'patient'|'yours'|'processing'
export const direction:      Computed<'en->es'|'es->en'|null>;
export const canRequestRepeat: Computed<boolean>;
export const canPause:       Computed<boolean>;          // false in assessment mode
export const transcriptItems: Computed<TranscriptItem[]>;
export const scoreSummary:   Computed<{ clean: number; withFindings: number; critical: number; unscored: number }>;
```

`turnState` is derived from `SessionView.state`, not carried as its own field:

| `SessionView.state` | `turnState` |
|---|---|
| `source_speaking` + active speaker `clinician` | `clinician` |
| `source_speaking` + active speaker `patient` | `patient` |
| `awaiting_rendering`, `rendering_capturing` | `yours` |
| `turn_closing` | `processing` |
| `armed`, `paused`, `debrief`, terminal | encounter chrome handles it; no turn state |

Chart mode (radar / bars / table) persists to settings, because a trainee who needs the table view needs it every time and re-selecting it on every report is a small, repeated accessibility tax.

### 5.5 Type generation

`src/types/api.ts` is **generated**, not hand-written: `make frontend-types` runs `datamodel-code-generator`'s JSON-Schema export from the backend Pydantic models through `json-schema-to-typescript`. CI fails if the checked-in file differs from a fresh generation. Hand-editing it is a merge conflict waiting to be resolved wrongly.

---

## 6. Real-time transport

### 6.1 Channels

| Channel | Direction | Payload | Purpose |
|---|---|---|---|
| `WS /ws/session/{id}` | duplex | JSON text frames | The event projection + client control (`docs/03-system-architecture.md` §13.3) |
| `WS /ws/audio/{id}` **[proposed]** | client → server | binary frames, 20 ms PCM | Trainee microphone capture (§7.3) |
| `HTTP /api/*` | request/response | JSON | Everything not real-time |
| `<audio>` + `MediaSource` **[open]** | server → client | Opus/PCM stream | TTS playback (§7.6) |

The audio uplink is a **second socket**, not multiplexed onto the event socket [proposed]. Reasons: a 20 ms binary frame cadence interleaved with JSON control frames makes both harder to reason about; the event socket must survive an audio-device fault without dropping; and backpressure policies differ — audio frames are droppable-newest-wins, event frames are never droppable. `docs/05-voice-pipeline.md` owns the final decision on the wire format; this document owns the browser side of whatever it decides.

### 6.2 Envelopes

```ts
// server → client
interface ServerEnvelope {
  t: EventKind;                 // docs/03-system-architecture.md §10.2
  seq: number;                  // global monotonic; the resume cursor
  turn: number | null;
  d: Record<string, unknown>;   // kind-specific payload
}

// client → server
type ClientEnvelope =
  | { t: 'start';  d: {} }
  | { t: 'pause';  d: {} }
  | { t: 'resume'; d: {} }
  | { t: 'abort';  d: { reason: string } }
  | { t: 'repeat'; d: { turn: number } }
  | { t: 'ack';    d: { seq: number } };
```

`ack` is sent at most every 500 ms with the highest contiguously-applied `seq` — it lets the server bound its replay buffer and is not a delivery guarantee. Every envelope is validated by a generated type guard before it reaches `applyEvent`; a malformed envelope is logged, counted, and dropped, and never partially applied. Payloads from the socket are treated as **untrusted input** at the trust boundary, consistent with `docs/03-system-architecture.md` §12 — including scenario text, which is untrusted data by that document's boundary B3. All text is inserted via `textContent`; the codebase contains no `innerHTML` assignment outside the icon sprite, enforced by lint.

### 6.3 `SessionSocket`

```ts
// src/transport/ws.ts
export class SessionSocket {
  constructor(sessionId: string, opts?: { url?: string });
  connect(): void;
  send(env: ClientEnvelope): void;         // queued while disconnected, flushed on open
  close(code?: number): void;
  readonly status: Signal<ConnectionStatus>;
  onEnvelope(fn: (e: ServerEnvelope) => void): () => void;
}

type ConnectionStatus =
  | { kind: 'connecting' }
  | { kind: 'open' }
  | { kind: 'resyncing'; from: number; to: number }
  | { kind: 'reconnecting'; attempt: number; nextMs: number }
  | { kind: 'closed'; reason: string };
```

### 6.4 Reconnection

The resume protocol from `docs/03-system-architecture.md` §13.3 — *a reconnecting client sends its last seen `seq` and receives the gap* — is implemented as:

1. On open, send `{"t":"ack","d":{"seq": lastSeq}}` as the first frame. `lastSeq = 0` on a cold load, which requests the whole session and is a legitimate, cheap path (a session is on the order of hundreds of events).
2. The server replays `seq > lastSeq`. The client stays in `resyncing` until it receives a `seq` equal to the `to` bound advertised in the server's replay header frame, applying events without animating: `store/session.ts` sets `replaying = true`, and `<rehearsal-turn-state>` suppresses transitions while it is set. Animating 90 seconds of missed turns in 200 ms is disorienting and, in the encounter, actively harmful.
3. Backoff: `250, 500, 1000, 2000, 4000, 8000 ms`, then hold at 8 s indefinitely, each with ±20% jitter. There is no attempt cap — the server is on `localhost` and is expected back. A cap would abandon a live session because a process restarted.
4. `navigator.onLine === false` or `visibilitychange` to hidden pauses the backoff timer; returning to visible triggers an **immediate** attempt, bypassing the schedule.
5. A gap that cannot be served (server restarted with a truncated buffer, `seq` ahead of the client's by more than the buffer) triggers a **full refold**: `GET /api/sessions/{id}` returns the folded `SessionView`, the client replaces its state wholesale, and the socket resumes from the returned `lastSeq`. This is the always-correct fallback and is exercised in tests by killing the buffer deliberately.

### 6.5 What the trainee sees while disconnected

The session keeps running headless (`docs/03-system-architecture.md` §5) — this is the important fact and the UI must communicate it exactly.

| Elapsed disconnected | Encounter UI | Non-encounter UI |
|---|---|---|
| < 1.5 s | Nothing. Reconnects inside a normal turn gap; announcing it would be noise | Nothing |
| 1.5–10 s | `<rehearsal-connection-status>` shows "Reconnecting" with a static indicator. Transcript dims to 70% opacity to signal staleness. **No modal, no focus move** — the trainee may be mid-utterance | Inline "Reconnecting" chip |
| > 10 s | Adds, via the status live region: "Connection lost. The session is still running — your audio is still being recorded." Manual "Reconnect now" button appears | Chip becomes a banner with a retry action |
| Socket closed by server with a terminal reason | Encounter exits to the report or the failure screen with the server's stated reason | Route to error view |

The audio uplink socket dropping is a **different and more serious** condition: capture has actually stopped. It surfaces immediately as a degrade banner and follows the device-loss path (§7.7), because unlike the event socket it is not cosmetic.

---

## 7. Audio in the browser

### 7.1 The constraint that shapes this section

The live agents take the trainee's audio **natively** — there is no ASR stage in the critical path (`docs/03-system-architecture.md` §7). The browser's job is therefore narrow and unusually strict: **capture clean PCM and get it to the backend with minimal added latency, and add nothing of its own.** No Web Speech API, no client-side VAD decision, no client-side transcription. The browser is a microphone, a meter and a speaker.

### 7.2 Permission and device flow

```ts
// src/audio/capture.ts
export interface CaptureHandle {
  readonly deviceId: string;
  readonly level: Signal<number>;      // 0..1 smoothed RMS
  readonly clipping: Signal<boolean>;
  stop(): void;
}

export async function listInputDevices(): Promise<MediaDeviceInfo[]>;
export async function startCapture(deviceId?: string): Promise<CaptureHandle>;
export function permissionState(): Promise<PermissionState>;   // via navigator.permissions
```

Order of operations, and it matters:

1. `navigator.permissions.query({name:'microphone'})` first, to distinguish *never asked* from *denied*. `enumerateDevices()` before permission returns entries with empty `label`s, so the device picker is useless until a stream exists.
2. Request a stream with a **generic** constraint set to trigger the prompt, then re-enumerate to get labelled devices, then re-acquire on the selected device. Two `getUserMedia` calls is the cost of a usable picker; it is paid once, in pre-flight.
3. Constraints [decided]:

```ts
{
  audio: {
    deviceId: selected ? { exact: selected } : undefined,
    echoCancellation: true,     // headphones are required, but bleed still happens
    noiseSuppression: false,    // suppression mangles speech onsets the model needs
    autoGainControl: false,     // AGC destroys the level meter's honesty and shifts dynamics between turns
    channelCount: 1,
    sampleRate: 48000,          // a request, not a guarantee — read the real rate off the AudioContext
  },
  video: false,
}
```

`noiseSuppression` and `autoGainControl` are off deliberately. Both are designed for intelligibility to humans on a call, and both alter exactly the signal characteristics a native-audio model consumes. **[proposed]** — worth an A/B against `heard_verbatim` fidelity (`docs/08-evals.md`); if suppression measurably *improves* fidelity in a noisy clinic room, this flips, and the flag lives in Settings → Audio either way.

4. Selected `deviceId` is persisted, but **`deviceId` is not stable across browser profiles or permission resets**. On restore, match on `deviceId` first, then on `label`, then fall back to `default` and tell the trainee which device was chosen. Silently falling back to the laptop's built-in mic when the trainee expects their headset is exactly the "silent failure that ruins sessions" pre-flight exists to prevent (`docs/09-ui-ux.md` §5.2).

### 7.3 The capture graph

```
MediaStream ─► MediaStreamAudioSourceNode ─► AudioWorkletNode ("pcm-frame")
                                                    │
                                     port.postMessage ├─► { pcm: Int16Array }  → SessionAudioSocket (binary)
                                                      └─► { rms, peak }        → level Signal (throttled 20 Hz)
```

`AudioWorklet`, not `ScriptProcessorNode` [decided] — the deprecated node runs on the main thread and its jitter under a busy render is exactly the failure this product cannot absorb. The worklet runs on the audio render thread at 128-sample quantum, accumulates to 20 ms frames, converts float32 → int16 (clamped, no dithering), and posts transferables.

```ts
// src/audio/pcm-worklet.ts — runs in AudioWorkletGlobalScope
class PcmFrameProcessor extends AudioWorkletProcessor {
  // Accumulates 128-sample quanta into 20 ms frames at the context's actual sampleRate.
  // Emits { pcm: Int16Array } (transferred) and { rms, peak } for metering.
  // Resampling to the backend's expected rate is NOT done here — see below.
}
```

**Resampling [decided]:** the worklet does not resample. It reports `sampleRate` in its first message and the backend consumes the native rate. Client-side resampling in JS is a quality risk for no benefit when the consumer is a local process that already has a resampler. The frame header carries `{sampleRate, channels: 1, format: 's16le'}` once at stream open.

**Backpressure:** if `SessionAudioSocket.bufferedAmount` exceeds 3 frames' worth, frames are dropped **oldest-first** and a counter increments; sustained drops (>2% over 5 s) emit a client diagnostic and a degrade indicator. Dropping newest would corrupt the tail of an utterance, which is where interpreters most often place the information a grader checks.

### 7.4 Level metering

`rms` is smoothed with a one-pole filter (attack 0.15, release 0.5) and exposed at 20 Hz — fast enough to feel live, slow enough not to schedule 60 signal updates a second during a turn. `<rehearsal-level-meter>` draws on a `<canvas>` inside `requestAnimationFrame`, reading `handle.level.peek()` (never subscribing, so it never triggers the effect scheduler). Clipping latches for 800 ms on any sample ≥ 0.99 so a brief clip is visible.

The meter is `aria-hidden`. Its information is delivered to screen-reader users by the pre-flight step's textual outcome ("Input detected at a good level") and, during the encounter, by the turn-state announcement — a continuously-updating live region for a level meter would be unusable.

### 7.5 The headphone check

Implements `docs/09-ui-ux.md` §5.2 step 2. There is no browser API that detects headphones; this is therefore an honest human confirmation, built to make the confirmation meaningful rather than reflexive:

1. Play a 2-second, 440 Hz, −18 dBFS tone through the selected **output** device (`HTMLMediaElement.setSinkId()` where available; Chromium yes, Safari no — see §11.1 and the assumption in §14).
2. While the tone plays, keep capture running and measure input RMS. If the input rises above a noise floor + 12 dB during tone playback, the tone is being picked up by the microphone: **the trainee is not on headphones**. Show that specific finding, not a generic prompt.
3. The trainee confirms explicitly ("I heard the tone in my headphones"). The confirmation is a real gate — `begin` stays `disabled` — but it is a human assertion and is recorded as one.
4. The measurement in step 2 is a **strong hint, not a verdict**: a loud room, an open-back headphone, or a directional mic can all defeat it in either direction. It never blocks on its own; it only changes the wording of the ask.

This is the one place the frontend runs a heuristic rather than displaying a server decision, and it is confined to a pre-flight gate whose consequences are recoverable.

### 7.6 Playback

TTS audio arrives streamed and must be interruptible within 120 ms (`docs/03-system-architecture.md` §5, §6.4 `barge_in_stop_ms`). The browser side:

- Playback through a `MediaSource`-fed `<audio>` element, or via `AudioBufferSourceNode` chunks on the same `AudioContext` as capture. **[open]** — `MediaSource` is simpler but its stop latency is not reliably under 120 ms across engines; a Web Audio path gives sample-accurate stop but requires manual chunk scheduling. **Resolution path:** measure both on the target machines with the harness in `docs/08-evals.md`; the one that meets `barge_in_stop_ms` at p95 wins. `docs/05-voice-pipeline.md` is the owning document.
- **The server decides barge-in, not the client.** The client does not stop playback on detecting local speech; it stops when `tts.interrupted` arrives. A client that made this decision locally would produce a session record that disagrees with the event log about when the trainee started speaking — and that offset is scored data.
- The `AudioContext` requires a user gesture to start. It is created and `resume()`d on the pre-flight "begin" click, never lazily at first playback, so the first utterance of an encounter is never the one that fails.

### 7.7 Device loss

`MediaStreamTrack.onended` / `ondevicechange` → immediately send nothing (the server owns state), surface the loss, and follow `docs/03-system-architecture.md` §8.2: the session moves to `paused` with a 10-second recovery window. The UI shows the countdown, offers device re-selection inside the window, and states plainly what happens at zero. On recovery, capture is re-acquired on the same `deviceId` if present.

---

## 8. Component state tables

The required per-component state matrix. Columns are the six canonical states; a cell reading "n/a" means the state is structurally impossible for that component and no code should exist for it.

### 8.1 Encounter components

| Component | Default | Loading | Streaming | Error | Empty | Disabled |
|---|---|---|---|---|---|---|
| `<rehearsal-turn-state>` | Current state, panel raised | n/a (state is always known once armed) | Speaking/capture indicator animates; suppressed while `replaying` | Unknown state → falls back to `processing` + status announcement | n/a | n/a |
| `<rehearsal-speaker-panel>` | Idle, name badge outline | Skeleton on first mount only | Utterance appends on `source.emitted` | Panel keeps last known content + stale tint | "Waiting to begin" | n/a |
| `<rehearsal-level-meter>` | Silent floor bar | "Waiting for microphone" | Live level; static bar under reduced motion | "No input detected" + remedy text | n/a | Greyed when capture stopped |
| `<rehearsal-directional-cue>` | "Interpret to Spanish" / "to English", 40px | n/a | n/a (never animates) | Hidden if direction unknown — a **wrong** cue is worse than none | n/a | n/a |
| `<rehearsal-transcript>` | Committed items, follow on | Skeleton rows ×3 | Appends; auto-scroll unless user scrolled up | Inline "Some turns could not be loaded" row, rest still shown | "The encounter has not started" | Selection still allowed |
| `<rehearsal-coach-card>` | Hidden | n/a | Enters between turns, 300 ms | Malformed payload → not rendered, counted | n/a | Suppressed at cap or in assessment mode |
| `<rehearsal-mode-badge>` | practice / assessment | n/a | n/a | n/a | n/a | n/a |
| `<rehearsal-degrade-banner>` | Hidden at L0 | n/a | n/a | Level + reason, never dismissible | n/a | n/a |
| `<rehearsal-connection-status>` | Hidden when open | "Connecting" | "Resyncing n events" | "Connection lost — session still running" + retry | n/a | n/a |

### 8.2 Assessment components

| Component | Default | Loading | Streaming | Error | Empty | Disabled |
|---|---|---|---|---|---|---|
| `<rehearsal-source-diff>` | Source + rendering, spans marked | Both blocks skeleton | n/a — renders only committed text | `SPAN_OUT_OF_RANGE` notice, unmarked text still shown in full | Rendering empty → "No rendering was produced for this turn" (a full omission, labelled as one) | Read-only in trainee view |
| `<rehearsal-finding-card>` | Icon + severity + type + spans + why-it-matters | Skeleton | n/a | Unknown `kind` → renders raw kind + "unrecognised category", never hidden | n/a | Override controls absent outside trainer view |
| Turn (scored, clean) | Green check + "No findings this turn" | — | — | — | — | — |
| Turn (**unscored**, `verdict === null`) | "Not yet scored" + neutral icon. **Never a clean confirmation** | Pending spinner while queue drains | — | — | — | — |
| Turn (**partial**, L2 degradation) | "Critical checks only — register and pragmatics were not assessed" | — | — | — | — | — |
| `<rehearsal-competency-chart>` | Radar (default), bars, or table | Skeleton polygon | n/a | "Chart could not render" + automatic table fallback | "Complete a session to see competencies" | Radar disabled with <3 dimensions; bars used instead |
| `<rehearsal-trend-chart>` | Multi-series lines | Skeleton axes | n/a | Table fallback | "Complete two sessions to see a trend" | — |
| `<rehearsal-confidence-disclosure>` | Always fully visible | Metrics pending → "Agreement figures loading" | n/a | "Agreement figures unavailable" — the section still renders | n/a | **Never disabled, never collapsible** |

### 8.3 Navigation, library and trainer components

| Component | Default | Loading | Streaming | Error | Empty | Disabled |
|---|---|---|---|---|---|---|
| `<rehearsal-scenario-card>` | Title, setting, turns, difficulty, skills | Skeleton card | n/a | "Scenario metadata incomplete", card not selectable | n/a | Locked → reason shown, never a bare lock icon |
| `<rehearsal-preflight-step>` | Pending | "Checking…" + `aria-busy` | n/a | Specific remedy string incl. the exact OS settings path | n/a | Disabled until the previous step passes |
| `<rehearsal-device-picker>` | Labelled device list | "Requesting permission" | n/a | "Microphone blocked — enable in System Settings › Privacy & Security › Microphone" | "No input devices found" | Disabled during an active capture |
| `<rehearsal-review-item>` | Learner, scenario, flagged count, status | Skeleton row | Status updates via polling | Row marked unloadable, queue still renders | "No sessions awaiting review" | Disabled while another item is open |
| `<rehearsal-empty-state>` | Title + body + optional action | n/a | n/a | n/a | This *is* the empty state | n/a |

---

## 9. Routing

Hash-based (`#/…`), because the app is served from a static mount and history-API routing would need a server catch-all for no benefit.

| Route | View | Guard |
|---|---|---|
| `#/` | `practice-view` (scenario picker) | — |
| `#/preflight/{sessionId}` | `preflight-view` | Session must be `armed` |
| `#/session/{sessionId}` | `encounter-view` | Session must be live; otherwise redirect to report |
| `#/report/{sessionId}` | `report-view` | Session must be `debrief`/`review`/`complete`/`aborted` |
| `#/progress` | `progress-view` | — |
| `#/library` | `library-view` | — |
| `#/review` / `#/review/{sessionId}` | `review-view` | Trainer role |
| `#/settings/{section?}` | `settings-view` | — |

Navigating away from a live encounter triggers the same confirmation as `Esc` (`docs/09-ui-ux.md` §5.3) via a `beforeunload` handler plus an in-app router guard. `beforeunload` alone is insufficient — hash changes do not fire it.

---

## 10. Accessibility implementation

`docs/09-ui-ux.md` §6 states the obligations. This section is how each is met in code.

### 10.1 Focus management across turn changes

**The rule: focus never moves during an active turn.** Implementation:

```ts
// src/views/encounter-view.ts
const FOCUS_SAFE_STATES: SessionState[] = ['awaiting_rendering', 'turn_closing', 'paused', 'debrief'];
// Any programmatic focus() call inside the encounter passes through requestFocus(),
// which queues the move until turnState() !== 'yours'. There is exactly one focus
// authority in the encounter view; no component calls focus() directly.
```

- Between turns, focus moves to the newly-enabled primary action if and only if the trainee's focus is currently on `document.body` (i.e. they have not deliberately focused something else). Stealing focus from someone reading the transcript is worse than not moving it.
- `<rehearsal-coach-card>` never takes focus on appearance. It is announced in the status region and is reachable by `Tab`.
- Modals (`exit confirmation`, `keyboard help`) use `<dialog showModal()>`, which gives native focus trapping and `Esc` handling. Focus returns to the invoking element on close — `<dialog>` does this natively; do not reimplement it.
- Focus rings: `:focus-visible { outline: var(--focus-width) solid var(--focus-color); outline-offset: var(--focus-offset); }`. There is no `outline: none` anywhere in the codebase; a lint rule enforces it.

### 10.2 Reading order in a bilingual view

DOM order in the encounter is **clinician → trainee → patient**, matching the visual left-centre-right and the physical triad (`docs/09-ui-ux.md` §1). CSS grid never reorders relative to source; `order` and `grid-auto-flow: dense` are prohibited in `layout.css` because they desynchronise the visual and screen-reader orders.

`lang` is applied at the element that owns the text, not the document:

```html
<rehearsal-speaker-panel lang="en">   <!-- inherits to every utterance inside -->
<rehearsal-transcript class="renderings">
  <li lang="es">Tome una pastilla dos veces al día…</li>   <!-- per-item, because -->
  <li lang="en">Take one tablet twice a day…</li>          <!-- the centre column alternates -->
</rehearsal-transcript>
```

The centre column is the case that requires per-item `lang`: the trainee's renderings alternate language turn by turn. A single `lang` on that column would have a screen reader read Spanish with English phonology for half the session — the precise failure `docs/09-ui-ux.md` §6 names as making the tool unusable.

Findings mix languages inside one sentence ("'twice a day' → 'al día'"). Each quoted span carries its own `lang` on an inline `<span>`; the surrounding explanatory text carries the **UI locale**, which may be neither.

### 10.3 Live regions

| Region | `aria-live` | Content | Never |
|---|---|---|---|
| `#turn-announcer` | `polite`, `aria-atomic="true"` | "Clinician speaking." / "Your turn. Interpret to Spanish." / "Processing." | Never `assertive` — it would interrupt the trainee mid-utterance |
| `#status-announcer` | `polite` | Degradation entered/exited, connection lost/restored, coach available, notes saved | Never scores during an encounter |
| Report summary | `role="status"` on load | "Report ready. 4 turns with findings, 1 critical." | — |

Rules that are easy to get wrong and are therefore stated:

- Announce **only on change**. `<rehearsal-turn-state>` compares against its previous value and writes the region only on a genuine transition; a re-render with the same state writes nothing.
- The turn announcement **always includes the direction**, because a blind trainee cannot read it off the layout.
- During `replaying`, live regions are muted entirely and a single summary is written at the end: "Reconnected. 6 turns while you were disconnected."
- **Scores never announce during an encounter** — the same rule as the visual design (`docs/09-ui-ux.md` §1 constraint 2). Verdicts land in the store during the session; the report reads them afterwards.
- Announcement text comes from the i18n catalogue in the **UI locale**, with the interpreted-into language named in that locale ("Interprete al español" / "Interpret to Spanish").

### 10.4 Keyboard map

From `docs/09-ui-ux.md` §6, with implementation notes:

| Key | Action | Notes |
|---|---|---|
| `Space` | Push-to-talk (hold) | Configurable to toggle in Settings (motor accessibility). `preventDefault` only when the encounter view is focused and the target is not a text input |
| `R` | Request repetition | Ignored while an input or the notes pad has focus |
| `N` | Toggle notes pad | Same guard |
| `J` / `K` | Move down / up through transcript scrollback | Moves a roving `tabindex` between transcript items; the focused item is read by the screen reader |
| `Esc` | Exit, with confirmation | Handled by the view, not by individual components |
| `?` | Keyboard help overlay | `<dialog>`; lists this table, generated from the same source as the handler map so it cannot drift |
| `Tab` / `Shift+Tab` | Standard order: header → clinician panel → trainee column → patient panel → footer actions | No positive `tabindex` anywhere |

Every single-key shortcut is registered on a single delegated `keydown` listener on the encounter root, with one guard function `isTypingTarget(e.target)`. Scattering `keydown` handlers across components is how single-letter shortcuts start firing inside text fields.

### 10.5 Charts

Every chart has a table view toggle that renders a real `<table>` with `<caption>` and `<th scope>` — not an ARIA-decorated `<div>`. Chart series are distinguished by line style *and* colour, and bars by pattern fill (SVG `<pattern>`) *and* colour. Tooltips activate on hover **and** on keyboard focus of the point/bar, which requires each mark to be focusable — a `<g tabindex="0" role="img" aria-label="…">` per mark.

### 10.6 Text scale and zoom

Layout is verified at 200% browser zoom and at `--text-scale: 1.3` with Spanish strings, at every breakpoint, with no horizontal scroll (`docs/09-ui-ux.md` §8). Paired bilingual panels are equal-width and independently scrollable, never content-sized — that is a layout rule with an accessibility consequence, so it is asserted in a test.

### 10.7 Targets

`--target-min: 44px` and `--target-gap: 8px` apply to every interactive element including transcript items, chart marks and span marks. Where a visual affordance must be smaller (a span mark inside running text), the hit area is expanded with padding and negative margin, not by shrinking the requirement.

### 10.8 Verification

| Layer | Method |
|---|---|
| Mechanical (contrast, roles, labels, duplicate ids) | `axe-core` assertion in every component test; CI fails on any violation |
| Contrast, both themes, both contrast modes | Token-pair snapshot test computing WCAG ratios over the full token matrix; fails below 4.5:1 body / 3:1 large-and-UI |
| Keyboard-only walkthrough | Manual script per screen, in the release checklist |
| Screen reader, bilingual | Manual: VoiceOver (macOS, primary target) and NVDA, with **both** UI locales, verifying Spanish is pronounced as Spanish |
| Reduced motion | Automated: `prefers-reduced-motion` emulation + assertion that no element has a running animation |

Automated tools catch roughly the mechanical half. The bilingual screen-reader pass is manual and is not optional, because it is the check that the automated tools cannot express.

---

## 11. Internationalisation

### 11.1 The two independent axes

The distinction that must never blur:

| Axis | What it is | Values | Controlled by |
|---|---|---|---|
| **UI language** | The language of the application's own chrome, labels, findings explanations, announcements | `en-US`, `es-MX` | Settings → Language; persisted |
| **Encounter languages** | The languages *spoken inside the simulation*: clinician English, patient Spanish | Fixed per scenario | The scenario, never the user |

A trainee may run the interface in Spanish while interpreting into English. Nothing in the codebase may derive one from the other. Concretely: `document.documentElement.lang` is the **UI locale**; encounter content carries its own `lang` per element (§10.2); `Intl` formatters are constructed with the **UI locale**; and the `direction` cue names the target encounter language *in the UI locale*.

### 11.2 Catalogue

ICU MessageFormat, one flat JSON file per locale, dot-namespaced keys:

```json
{
  "encounter.cue.toSpanish": "Interpret to Spanish",
  "encounter.turn.announce": "{speaker, select, clinician{Clinician speaking} patient{Patient speaking} you{Your turn. Interpret to {target}.} other{}}",
  "report.summary.findings": "{n, plural, =0{No findings} one{# finding} other{# findings}} across {turns, plural, one{# turn} other{# turns}}",
  "finding.kind.omission": "Omission",
  "finding.why.frequency": "Frequency errors can change how a patient takes medication.",
  "preflight.mic.blocked": "Microphone blocked. Enable it in System Settings › Privacy & Security › Microphone, then try again."
}
```

```ts
// src/i18n/index.ts
export type Locale = 'en-US' | 'es-MX';
export function setLocale(l: Locale): Promise<void>;   // loads catalogue, updates <html lang>, re-renders
export function t(key: string, vars?: Record<string, unknown>): string;
export const locale: Signal<Locale>;
export function formatNumber(n: number, opts?: Intl.NumberFormatOptions): string;
export function formatPercent(n: number): string;
export function formatDuration(ms: number): string;
```

`MessageFormat` instances are compiled once per key per locale and cached — recompiling ICU patterns inside a render loop is a real cost in the transcript.

### 11.3 Rules

- **Both catalogues ship complete from the start.** CI fails if the key sets differ (`make i18n-check` diffs the two files' key sets and the placeholder sets within each message). There is no English-first phase (`docs/09-ui-ux.md` §7).
- **No machine translation.** Spanish strings are written or reviewed by a bilingual speaker, tracked in the catalogue's sibling `es-MX.review.json` recording who reviewed which keys. The users are language professionals.
- **No string concatenation.** Every user-visible sentence is one catalogue entry with placeholders. Concatenated fragments cannot be reordered for Spanish syntax.
- **Numbers, percentages and durations go through `Intl`**, never through template literals. Spanish uses `,` as the decimal separator, and a fidelity score rendered as `0.87` to a Spanish-locale user is wrong.
- **Error taxonomy names are catalogue keys**, not raw enum values. `omission` is a wire value; "Omisión" is what a user reads.
- **Locale switching is instant and requires no reload.** `locale` is a signal; every component that renders text subscribes to it. Tested by switching locale mid-session and asserting the live regions announce in the new locale from the next turn onward.
- **Spanish expansion (15–25%)** is a layout test, not a hope: the visual regression suite runs every screen in `es-MX` at `--text-scale: 1.3`.

### 11.4 Browser targets

Chromium ≥ 111 and Safari ≥ 16.4 on macOS (the platform this ships on — MLX on Apple Silicon). Both have `AudioWorklet`, `Intl.Segmenter`, `<dialog>`, container queries and CSS nesting. `setSinkId` is Chromium-only; §7.5 degrades to the system default output on Safari with a stated note in the pre-flight step. No transpilation below ES2022; no polyfills.

---

## 12. Performance

### 12.1 Budgets

These are budgets, not aspirations: CI fails the build on the bundle numbers, and the runtime numbers are asserted by a Playwright trace assertion on the encounter view.

| Budget | Target | Hard fail | Measured by |
|---|---|---|---|
| JS bundle, gzipped, initial route | ≤ 120 kB | 160 kB | `vite build` + `rollup-plugin-visualizer` in CI |
| CSS, gzipped | ≤ 20 kB | 30 kB | same |
| Fonts (Figtree + Noto Sans, subset) | ≤ 180 kB total, woff2 | 240 kB | `make fonts` reports |
| First contentful paint (localhost, cold) | ≤ 400 ms | 800 ms | Playwright trace |
| Encounter view interactive from route change | ≤ 250 ms | 500 ms | Playwright trace |
| Main-thread work per socket envelope | ≤ 4 ms | 16 ms | `performance.measure` around `applyEvent` + flush |
| Longest task during a live turn | ≤ 50 ms | 100 ms | Long Tasks API, asserted over a scripted 20-turn session |
| Level-meter frame cost | ≤ 2 ms | 4 ms | rAF instrumentation |
| Transcript append (500 committed turns) | ≤ 8 ms | 16 ms | Benchmark test |
| Steady-state heap after a 40-turn session | ≤ 60 MB | 100 MB | `performance.memory` sample in the soak test |

**The encounter budget is the one that matters.** Everything else can be slow and merely annoying; a long task during a live turn drops audio frames or stalls the meter while a human is speaking under cognitive load.

### 12.2 Fonts

Figtree and Noto Sans are **self-hosted and subset** — no external font CDN (there is no network in this deployment, and a font request to a third party from a tool handling clinical training content is a privacy problem regardless, see `docs/12-security-privacy.md`). Subsetting keeps Latin + Latin-1 Supplement + Latin Extended-A (covers every Spanish diacritic, `¿`, `¡`, and the Mixteco/Triqui orthographies' Latin base) and drops Cyrillic/Greek. `font-display: swap`, preloaded in `index.html` for the two weights used above the fold.

### 12.3 Splitting

One chunk for the app shell + practice/preflight/encounter; a lazy chunk for report + progress + review, which pull `uplot` and the chart components. The encounter must never pay for the charting code. `library` and `settings` are in the shell — they are small and reachable from a cold start.

### 12.4 Virtualisation

`docs/09-ui-ux.md` §8: *long transcripts virtualise beyond 100 turns*. Implementation:

- Below the threshold, `<rehearsal-transcript>` renders every item. Virtualisation has a real cost in selection, find-in-page and screen-reader completeness, and it is not paid until it must be.
- At or above 100 items, it switches to a **windowed list**: a fixed-height scroll container, absolutely-positioned items, and an `IntersectionObserver`-driven window of `visible + 12` items above and below. Item heights are measured and cached on first render (they vary — Spanish runs longer), with an estimated height for unmeasured items and correction on measure.
- Accessibility of a windowed list is a known hazard, handled explicitly: the container is `role="log"` with `aria-setsize` and each item `aria-posinset`, so a screen reader reports "item 112 of 340" rather than "item 4 of 12". `J`/`K` navigation scrolls unmounted items into the window before focusing them.
- **Find-in-page breaks under virtualisation.** Mitigation: the report view (where searching is likely) renders un-virtualised up to 500 turns, and a filter control is provided rather than relying on browser find. Stated as a limitation in Settings → Accessibility. **[decided]**

### 12.5 Rendering discipline in the encounter

- Turn-state transitions animate `transform` and `opacity` only. No `width`, `height`, `top` or `box-shadow` animation — each forces layout or paint on a surface that must stay at 60 fps.
- The level meter's canvas is `will-change: transform` and sized once on resize, never per frame.
- Transcript appends use a `DocumentFragment` and a single insertion.
- `content-visibility: auto` on collapsed report turn sections.
- The effect scheduler coalesces on a microtask, so an envelope burst produces one DOM flush (§5.1).

---

## 13. Error, degradation and offline behaviour

### 13.1 Error taxonomy (client-side)

| Class | Example | Behaviour |
|---|---|---|
| **Transport** | Socket closed, fetch failed | §6.5. Non-blocking in the encounter; retry with backoff; never a modal during a live turn |
| **Contract** | Envelope fails its type guard, span offset out of range, unknown enum | Log with `console.error` + counter, render the safe degradation (§3.4 rule 6, §8.2), never crash the view |
| **Permission** | Microphone denied | Specific remedy with the exact OS path; blocks pre-flight, never a generic "Audio error" |
| **Device** | Mic unplugged mid-session | §7.7 — pause + 10 s recovery window + countdown |
| **Server degradation** | `degraded.entered` L1–L5 | `<rehearsal-degrade-banner>`, non-dismissible, plus the per-level trainee-facing text from `docs/03-system-architecture.md` §14 |
| **Render** | An unexpected exception inside a component | Component-level boundary: the component replaces itself with an inline error card naming what failed; siblings keep rendering. The encounter's turn state and level meter are **never** unmounted by a sibling's failure |

Global `window.onerror` and `unhandledrejection` handlers write to a client diagnostics ring buffer (last 200 entries, in memory) exported by Settings → Models → "Export diagnostics", alongside the server's own diagnostics. They do not display a global error screen during an encounter.

### 13.2 Offline

The app is served from `127.0.0.1`; "offline" in the usual sense does not occur, and there is **no service worker** [decided] — a stale cached shell talking to a live event log is a source of subtle wrongness for zero benefit on a local mount.

What does occur, and is handled:

| Condition | Behaviour |
|---|---|
| `rehearsal-api` restarted mid-session | Socket reconnects, resumes by `seq`, and the backend's own crash-resume (`docs/03-system-architecture.md` §8.3) reopens the abandoned turn. The UI shows "Reconnecting", then folds the gap. No client action required |
| API down at cold load | Full-page state: "Rehearsal is not running" with the exact command to start it. Not a spinner |
| Browser tab backgrounded during an encounter | `AudioWorklet` continues (audio contexts are not throttled by visibility on macOS), but rAF stops so the meter freezes. On return to visible, the meter resumes and a status announcement states nothing was lost. The session was never client-driven |
| Machine sleeps mid-session | On wake, socket is dead → immediate reconnect → server has since paused or aborted per its own rules. The UI renders whatever the server says, and never guesses |

### 13.3 The rendering rules that are non-negotiable

Three assertions with tests attached, because getting them wrong misrepresents an assessment of a person:

1. `verdict === null` never renders as a clean turn.
2. `verdict.status !== 'complete'` always renders the "not assessed" qualifier for the semantic categories, and never the phrase "no errors".
3. `degrade.level > 0` always renders the banner, and the session report always carries `degrade_max` — a number produced at L2 is not comparable to one produced at L0 (`docs/03-system-architecture.md` §14).

---

## 14. Assumptions, open questions and dependencies

Points where this document had to decide something the rest of the project should know about, or where it is waiting on a sibling document.

| # | Item | Status | Notes / resolution path |
|---|---|---|---|
| A1 | **Audio uplink is a second WebSocket** `/ws/audio/{session_id}`, binary, 20 ms s16le frames | **[proposed]** | `docs/03-system-architecture.md` §13.3 defines only the JSON event socket. The browser must get PCM to the backend somehow, and multiplexing it onto the event socket harms both. Owning document for the final wire format: `docs/05-voice-pipeline.md` |
| A2 | **No client-side resampling**; the backend consumes the `AudioContext`'s native rate, advertised in a stream-open header | **[proposed]** | Assumes the backend has a resampler. If it does not, this flips and the worklet gains a polyphase resampler — a measurable quality cost |
| A3 | **TTS playback path** (`MediaSource` vs Web Audio chunk scheduling) | **[open]** | Decided by measuring `barge_in_stop_ms` p95 on target hardware. See §7.6 |
| A4 | **`noiseSuppression` and `autoGainControl` are off** | **[proposed]** | Assumes raw audio serves a native-audio model better than call-optimised audio. Falsifiable against `heard_verbatim` fidelity in `docs/08-evals.md`; exposed as a Settings flag either way |
| A5 | **`setSinkId` is Chromium-only**, so the headphone check plays through the system default output on Safari | **[decided]** | Stated in the pre-flight step text. Not worth a workaround |
| A6 | **A second `fold` implementation exists in TypeScript** | **[decided, with mitigation]** | Divergence from the Python fold is a genuine risk. Mitigated by the shared fixture `test/fixtures/fold-cases.json` asserted from both sides (§5.3). The alternative — server-rendered view models over the socket — was rejected because it puts render concerns in the orchestrator |
| A7 | **Notes are persisted via `POST /api/sessions/{id}/notes`** | **[proposed]** | `docs/09-ui-ux.md` §5.3 requires notes in the session record; `docs/03-system-architecture.md` §13.3 lists no such endpoint and §10.2 no such event. Proposed: endpoint + `note.saved` event kind |
| A8 | **A `review` role exists** to gate `#/review` | **[open]** | `docs/09-ui-ux.md` §5.7 describes a trainer, but single-user local deployment has no auth. Interim: the route is reachable and unguarded on a local install; a real gate belongs to `docs/12-security-privacy.md` |
| A9 | **Turn-count and elapsed timer are `aria-hidden`**, delivered via the turn live region instead | **[decided]** | A continuously-updating timer in the accessibility tree is announced by some screen readers and would talk over a trainee mid-utterance |
| A10 | **Find-in-page is degraded** in virtualised transcripts over 100 turns | **[decided]** | Filter controls provided instead; limitation stated in Settings. Revisit if trainees report searching transcripts as a primary workflow |
| A11 | **Recommendation reasons** rendered by `<rehearsal-scenario-card>` come from the learner model | **[open]** | `docs/09-ui-ux.md` §5.1 requires the reason to be always visible. The payload shape is not yet defined; assumed `{ reason_key: string, vars: Record<string, unknown> }` so the reason is a catalogue entry and therefore bilingual, not a server-generated English sentence |

---

## 15. Definition of done for a frontend change

- [ ] No literal colour, duration, radius or spacing outside `tokens.css`
- [ ] Every new user-visible string exists in **both** catalogues; `make i18n-check` passes
- [ ] Every new text node carrying encounter content has a correct `lang`
- [ ] `axe-core` clean; contrast snapshot passes in light, dark and high-contrast
- [ ] Keyboard-reachable, focus-visible, ≥44px target
- [ ] Behaviour specified for all six states in §8, or the state marked structurally impossible
- [ ] No `innerHTML`; all socket payload treated as untrusted
- [ ] If it renders a verdict: the three non-negotiable rules in §13.3 hold, with a test
- [ ] Bundle budget unchanged or the delta justified in the PR
- [ ] If it touches the encounter: long-task assertion still passes over the scripted 20-turn session
