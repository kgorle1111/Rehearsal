# 09 — Interface & Experience Design

The complete interaction and visual design for Rehearsal. This document defines *what the interface is and why*; `docs/10-frontend-spec.md` defines *how it is built*.

---

## 1. Design thesis

Three constraints shape every decision here, and they are unusual enough to state up front:

**1. The interface must disappear during the encounter.** A trainee interpreting a live medical conversation is under genuine cognitive load — listening in one language, holding meaning in working memory, producing it in another, while tracking register and staying in first person. Any interface element that demands attention during a turn is stealing it from the skill being trained. During an encounter the UI does almost nothing: it shows *who is speaking*, *whose turn it is*, and nothing else that moves.

**2. Feedback is withheld until it can be acted on.** Scores never appear mid-encounter. Real interpreting has no scoreboard, and showing one would train the wrong reflex — watching the meter instead of the meaning. All assessment surfaces *after* the encounter, when the trainee can actually study it.

**3. The layout mirrors the physical reality.** Medical interpreting is a *triadic* encounter: clinician, patient, and interpreter positioned between them. The interface uses that same spatial arrangement — clinician left, patient right, the trainee's own output down the centre. This is not decoration; it gives the trainee a stable spatial model of who is speaking to whom, which is exactly the thing that collapses under load.

---

## 2. Design system

### 2.1 Palette

Chosen for a clinical-adjacent context: calm, high-legibility, no alarm colours except where alarm is meant.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--color-primary` | `#0891B2` | `#22D3EE` | Primary actions, active turn indicator |
| `--color-on-primary` | `#FFFFFF` | `#083344` | Text on primary |
| `--color-secondary` | `#22D3EE` | `#67E8F9` | Secondary emphasis |
| `--color-accent` | `#059669` | `#34D399` | Success, clean turns, competency gains |
| `--color-background` | `#ECFEFF` | `#0B1418` | App background |
| `--color-surface` | `#FFFFFF` | `#132025` | Cards, panels |
| `--color-foreground` | `#164E63` | `#E6F6FA` | Primary text |
| `--color-muted` | `#E8F1F6` | `#1B2C33` | Muted surfaces |
| `--color-muted-foreground` | `#64748B` | `#94A9B4` | Secondary text |
| `--color-border` | `#A5F3FC` | `#25404A` | Borders, dividers |
| `--color-destructive` | `#DC2626` | `#F87171` | Critical findings only |
| `--color-warning` | `#D97706` | `#FBBF24` | Non-critical findings |
| `--color-ring` | `#0891B2` | `#22D3EE` | Focus ring |

Dark mode uses desaturated tonal variants, contrast-tested independently. Light values are never simply inverted.

**Semantic finding colours** — used consistently everywhere a finding appears:

| Severity | Colour | Icon | Never |
|---|---|---|---|
| Critical (could change clinical action) | `--color-destructive` | filled alert-octagon | conveyed by colour alone |
| Non-critical | `--color-warning` | outline alert-triangle | conveyed by colour alone |
| Clean / accurate | `--color-accent` | check-circle | conveyed by colour alone |

Every finding carries icon + text label + colour. A colourblind trainee, a greyscale print, and a screen reader all receive the same information.

### 2.2 Typography

| Role | Font | Rationale |
|---|---|---|
| Headings | **Figtree** 500/600/700 | Clean, humanist, professional without being corporate |
| Body & all encounter text | **Noto Sans** 400/500/700 | Chosen deliberately: complete extended-Latin and Spanish diacritic coverage. A bilingual interface that renders *ñ, á, ü, ¿, ¡* inconsistently reads as careless to the exact users we are serving |
| Numerals in scores/tables | Noto Sans, `font-variant-numeric: tabular-nums` | Prevents column jitter as values change |

Type scale: 12 / 14 / 16 / 18 / 20 / 24 / 32 / 40. Body 16px minimum. Line height 1.5 body, 1.25 headings. Measure capped at 70 characters for reading surfaces; transcript columns cap at 55.

**Bilingual typography rules.** Spanish text runs ~15–25% longer than English for the same content. Every bilingual layout is built to that expansion without reflow: paired panels are equal-width and independently scrollable, never auto-sized to content. Language is marked with `lang="en"` / `lang="es"` at the element level so screen readers switch pronunciation — a detail that decides whether the tool is usable by a bilingual professional at all.

### 2.3 Spacing, radius, elevation, motion

Spacing scale (8pt rhythm): 4, 8, 12, 16, 24, 32, 48, 64.
Radius: 6px controls, 10px cards, 16px modals, full for pills.
Elevation: three levels only — flat, card (`0 1px 3px rgba(22,78,99,.08)`), overlay (`0 8px 24px rgba(22,78,99,.16)`).

Motion: 150ms micro-interaction, 200ms state change, 300ms panel transition. Ease-out entering, ease-in exiting, exits ~70% of enter duration. `transform`/`opacity` only. **`prefers-reduced-motion` removes all non-essential motion — including the waveform animation, which falls back to a static level bar.**

---

## 3. Information architecture

```
Rehearsal
├── Practice            → scenario picker → pre-flight → encounter → report
├── Progress            → competency over time, error patterns, session history
├── Library             → scenario bank, browse/preview/manage
├── Review   (trainer)  → queue of sessions awaiting human review
└── Settings            → audio devices, language, modes, accessibility, data
```

Navigation is a persistent left sidebar on ≥1024px, collapsing to a top bar with a menu below that. Navigation placement never changes between screens. The encounter screen is the sole exception: it takes over the full viewport and exposes only an exit affordance, because navigation chrome during an encounter is an attention leak.

---

## 4. The two modes

A single, prominent distinction that changes behaviour across the product:

| | **Practice mode** | **Assessment mode** |
|---|---|---|
| Coach interjections | On (configurable) | Off |
| Pause / replay a turn | Allowed | Not allowed |
| Request repetition | Unlimited, untracked | Allowed and **tracked** |
| Scores shown | After each turn (optional) | Only at session end |
| Session record | Marked *practice* | Marked *assessment*, eligible for trainer review |

Mode is chosen at session start and is visually unmistakable throughout — assessment mode carries a persistent, quiet marker in the encounter header. Blurring these two would let practice sessions leak into a performance record, which the responsible-use position in `docs/12-security-privacy.md` forbids.

---

## 5. Screens

### 5.1 Scenario picker

**Purpose:** choose what to practise, with enough information to choose deliberately and not enough to spoil the encounter.

Layout: a filter rail (specialty, difficulty, language variety, duration, skills targeted) beside a card grid. Each card shows: scenario title, clinical setting, estimated turns, difficulty band, the skills it targets (e.g. *numeric density*, *emotional register*, *idiom*), and — if practised before — a small competency delta from last attempt.

Deliberately **not** shown: the actual dialogue, the specific errors it is designed to elicit. Previewing content invalidates the encounter.

A "Recommended next" row sits at the top, populated by the learner model (`docs/16-roadmap.md`, Stage 4) with a one-line reason: *"Targets frequency expressions — your lowest-confidence skill."* The reason is always visible; a recommendation the trainee cannot interrogate is a black box.

States: loading (skeleton cards), empty (no scenarios — with the action to build the bank), filtered-empty (with a one-tap filter reset), error.

### 5.2 Pre-flight check

A short, unskippable gate before every encounter. It exists because the failure modes it prevents are silent and ruin sessions.

1. **Microphone** — device selector, live level meter, a 3-second "say something" confirmation.
2. **Headphones** — an explicit confirmation step. Without headphones the system's own speech is captured and scored as the trainee's interpretation. The check plays a short tone through the output device and asks the trainee to confirm they heard it *in headphones*. Blunt, and it prevents an entire class of corrupted sessions.
3. **Model readiness** — a quiet indicator that models are warm; if not, a progress state rather than a stall.
4. **Mode + scenario confirmation** — a final summary line.

Failure states are specific and actionable: *"No input detected — check that Rehearsal has microphone permission in System Settings"* with the exact path, not *"Audio error."*

### 5.3 The encounter — the core screen

The screen the whole product is judged on. Full-viewport, three-column on desktop, stacked on narrow.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ◀ Exit          Diabetes follow-up · Assessment mode        Turn 7      ⏱ 4:12│
├────────────────────────┬───────────────────────────┬─────────────────────────┤
│      CLINICIAN         │           YOU             │        PATIENT          │
│      English           │        interpreting       │        Español          │
│  ┌──────────────────┐  │                           │  ┌───────────────────┐  │
│  │ ● speaking       │  │   ┌───────────────────┐   │  │   listening       │  │
│  │                  │  │   │                   │   │  │                   │  │
│  │ "Take one tablet │  │   │   ▁▃▅█▅▃▁ level   │   │  │                   │  │
│  │  twice a day     │  │   │                   │   │  │                   │  │
│  │  with food."     │  │   │   YOUR TURN       │   │  │                   │  │
│  │                  │  │   │   → to Spanish    │   │  │                   │  │
│  └──────────────────┘  │   └───────────────────┘   │  └───────────────────┘  │
│                        │                           │                         │
│  ─ earlier turns ─     │   ─ your renderings ─     │   ─ earlier turns ─     │
│  (scrollback)          │   (scrollback)            │   (scrollback)          │
├────────────────────────┴───────────────────────────┴─────────────────────────┤
│   [ ⟲ Request repetition ]        [ ✎ Notes ]              [ ■ End session ]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Turn state is the only thing that animates.** Four states, each unmistakable at a glance and never signalled by colour alone:

| State | Visual | Audio | Announced to screen readers |
|---|---|---|---|
| Clinician speaking | Left panel raised, animated speaking indicator, name badge filled | AI voice (en-US) | "Clinician speaking" |
| Patient speaking | Right panel raised, same treatment | AI voice (es-MX) | "Patient speaking" |
| **Your turn** | Centre panel raised and outlined in primary; a directional cue "→ to Spanish" / "→ to English"; live level meter | soft cue tone | "Your turn. Interpret to Spanish." |
| Processing | Centre panel settles, subtle indeterminate indicator | silent | "Processing" |

The **directional cue** — which language to produce — is the single most important element on the screen. Under load, trainees interpret into the wrong language; the cue is large, persistent, and stated in words, not just implied by position.

**Live transcript.** Each panel holds its own scrollback: source utterances on the outside columns, the trainee's renderings down the centre, vertically aligned with the source they render. Scrollback auto-follows unless the trainee scrolls up, in which case it holds position and shows a "jump to current" control. Transcript text is selectable and copyable.

Transcript of the trainee's own speech appears **after** the turn commits, not word-by-word during it. Streaming a trainee's own words back at them mid-utterance is actively disruptive — it induces the same interference as delayed auditory feedback.

**Request repetition.** A first-class control, because asking for repetition is a *taught, legitimate professional technique*, not a failure. Pressing it makes the AI speaker repeat the last utterance. In practice mode it is untracked. In assessment mode it is recorded — appropriate use is neutral, systematic over-reliance surfaces in the report as a pattern, never as an error. This single design decision signals to a professional user that the system understands their craft.

**Notes.** Consecutive interpreting involves note-taking. A collapsible pad is available, persists per turn, and is included in the session record for the trainee's own review. Never scored.

**Coach interjections (practice mode only).** A distinct, non-modal card that slides into the centre column *between* turns, never during one. Dismissible, and capped — a coach that interrupts constantly trains dependence. Visually and structurally separate from findings, so guidance is never mistaken for assessment.

**Exit.** Confirms before discarding, offers "save partial session."

### 5.4 Turn review (practice mode, between turns)

An optional inline panel that appears between turns showing the previous turn's findings. Deliberately compact — full analysis belongs in the report.

The core component here and in the report is the **source-vs-rendering comparison**:

```
SOURCE (clinician, English)
  "Take one tablet twice a day with food."
                 ▔▔▔▔▔▔▔▔▔▔                        ← omitted span, marked
YOUR RENDERING (Spanish)
  "Tome una pastilla al día con comida."
                        ▔▔▔▔▔▔                      ← substituted span, marked

  ⛔ CRITICAL · Substitution — frequency
     "twice a day" → "al día" (once a day)
     Frequency errors can change how a patient takes medication.
```

Design rules for this component:
- The source and the rendering are always both fully visible. Never show only the error.
- Spans are marked with underline + background tint + an icon anchor — three independent channels.
- Every finding names the **error type**, the **severity**, the **exact spans**, and a **one-line reason it matters clinically**. A trainee who is told "substitution" learns nothing; one told "frequency errors change how a patient takes medication" learns something.
- Findings are ordered by severity, never by position in the sentence.
- Clean turns get a genuine, visible confirmation, not silence. Absence of feedback is not feedback.

### 5.5 Session report

The artefact a trainee actually studies, and the thing they may share with a trainer.

Structure, in order:

1. **Header** — scenario, mode, duration, turn count, date-free session identifier.
2. **At a glance** — turns clean vs with findings; critical-error count (the number that matters); a one-sentence plain-language summary generated from the findings, never a grade letter.
3. **Skill breakdown** — competency across the tracked dimensions (numeric fidelity, negation, register control, first-person discipline, completeness, idiom handling, medical lexicon). Radar chart **with a mandatory grouped-bar alternative toggle** — radar is good for shape recognition and poor for precise reading, and the accessibility guidance is explicit that it needs a fallback.
4. **Turn-by-turn** — the full transcript with inline findings, collapsible per turn, filterable by severity and error type.
5. **Patterns** — recurring findings across the session ("frequency expressions were dropped in 3 of 4 opportunities"). Patterns are more actionable than individual errors.
6. **What to practise next** — concrete, tied to specific scenarios in the library.
7. **Confidence and limits** — a short, permanent section stating how the scoring works, its measured agreement with human expert judgement, and what it is expected to be weakest at (register and pragmatics); this section prints *not yet measured* until per-category figures exist, then prints them. **This section is not optional and not collapsible.** A tool that assesses people must be honest about its own error rate on the same screen as the assessment.
8. **Export** — the trainee owns this record: export as PDF or structured JSON, and delete it.

### 5.6 Progress dashboard

Longitudinal view. The design risk here is turning a training tool into a performance-surveillance dashboard; the layout deliberately foregrounds *trajectory and next action* over *ranking*.

- **Competency over time** — multi-series line chart, one series per skill dimension, series distinguished by line style *and* colour. Time on the x-axis is measured in sessions, not calendar time.
- **Error taxonomy breakdown** — horizontal bar chart of finding counts by error type, split critical / non-critical. Horizontal because category labels are long and bilingual.
- **Critical-error trend** — a single prominent sparkline, because this is the safety-relevant number.
- **Session history** — sortable table with `aria-sort`, linking to reports.
- **Practice consistency** — a simple count of sessions, never a streak mechanic. Streaks manufacture guilt and, for a working health professional practising after shifts, that is a hostile design.

Chart rules throughout: legends always visible, tooltips on hover *and* keyboard focus, a table view toggle for every chart, subtle gridlines, locale-aware number formatting, meaningful empty states ("Complete two sessions to see a trend"), and never colour alone.

### 5.7 Trainer review queue

For a training program. A trainer reviews flagged turns and can **override the system's finding** — override is a first-class, expected action, not an exception path.

Layout: a queue list (learner, scenario, flagged-turn count, status) beside a review pane showing the same source-vs-rendering component with the finding, plus: *Agree* / *Disagree — not an error* / *Adjust severity* / *Add a finding the system missed*, each with an optional note.

Every override is recorded. Overrides are one of the most valuable signals the system produces: they are the live, ongoing measurement of grader accuracy against human expert judgement, and they feed directly into the evaluation record described in `docs/08-evals.md`. The UI says so explicitly to the trainer — people give better labels when they know the labels matter.

### 5.8 Settings

Grouped: **Audio** (devices, levels, test, headphone confirmation), **Language** (interface language — independent of encounter languages — plus preferred Spanish variety), **Practice** (default mode, coach behaviour and cap, repetition policy), **Accessibility** (reduced motion, text scale, high-contrast, transcript-only mode), **Data** (storage location, export everything, delete everything with a real confirmation), **Models** (active models, versions, warm-up, diagnostics export).

**Transcript-only mode** deserves naming: a fully text-based encounter path where the trainee types renderings instead of speaking. It exists for Deaf and hard-of-hearing users, for noisy environments, and as the degradation target when the voice pipeline cannot meet its latency budget (`docs/05-voice-pipeline.md`). It is a first-class mode, not a broken fallback, and it is scored by the same engine.

---

## 6. Accessibility

Beyond WCAG 2.1 AA, this product has specific obligations because of what it is.

**Bilingual screen-reader correctness.** Every text node carries `lang`. A screen reader must pronounce Spanish content in Spanish and English content in English; getting this wrong makes the tool unusable for the blind bilingual professionals who are among its most natural users.

**Live-region discipline.** Turn changes are announced via `aria-live="polite"` — never `assertive`, which would interrupt the trainee mid-utterance. Score updates never announce during an encounter. The directional cue ("interpret to Spanish") is announced on every turn change, because a blind user cannot rely on the spatial layout that carries this for sighted users.

**Focus management.** Focus never moves during an active turn. Between turns, focus moves predictably to the newly available action. Modals trap focus and return it on close. Focus rings are 2px, high-contrast, never removed.

**Keyboard map** (all encounter functions reachable without a mouse):

| Key | Action |
|---|---|
| `Space` | Push-to-talk (configurable to toggle) |
| `R` | Request repetition |
| `N` | Toggle notes |
| `J` / `K` | Move through transcript scrollback |
| `Esc` | Exit (with confirmation) |
| `?` | Keyboard help overlay |

**Motor accessibility.** Push-to-talk is configurable to a toggle so no interaction requires sustained holding. All targets ≥44×44px with ≥8px separation.

**Cognitive load.** One primary action per screen. Progressive disclosure in the report — the summary is readable in fifteen seconds, the detail is one interaction away. Plain-language finding explanations, in both interface languages, written at an accessible reading level and reviewed by a bilingual speaker rather than machine-translated.

---

## 7. Microcopy

Voice: precise, calm, respectful of expertise. The user is a professional or training to be one.

| Do | Don't |
|---|---|
| "Frequency changed: 'twice a day' → 'al día'" | "Oops! You made a mistake 🙈" |
| "This could change how the patient takes the medication." | "Critical failure" |
| "Interpret to Spanish" | "Go!" |
| "3 of 4 frequency expressions were dropped." | "You're bad at frequencies." |
| "No findings this turn." | (silence) |

Findings describe the *rendering*, never the person. "The rendering omitted the dosage," not "you forgot the dosage." Assessment language that attacks the trainee produces defensiveness, and defensive learners stop practising.

All user-facing strings exist in both interface languages from the start — there is no English-first phase. A bilingual tool that ships English-only strings with Spanish "coming later" tells its users exactly where they rank.

---

## 8. Responsive behaviour

| Breakpoint | Layout |
|---|---|
| ≥1440px | Full three-column encounter, sidebar nav, report side-by-side comparisons |
| 1024–1439px | Three-column encounter with narrowed side panels, sidebar nav |
| 768–1023px | Encounter becomes two-row: speakers above, trainee panel below; top-bar nav |
| <768px | Single-column stacked encounter; source-vs-rendering comparisons stack vertically with clear labels; charts switch to horizontal bars; the report becomes a vertical scroll |

The encounter is usable on a tablet — a realistic device for a clinic-based trainee — but the primary target is a laptop, because sustained voice practice with headphones is a seated activity.

No horizontal scroll at any width. Long transcripts virtualise beyond 100 turns.

---

## 9. Component inventory

| Component | Used in | Key states |
|---|---|---|
| `TurnStateIndicator` | Encounter | clinician / patient / your-turn / processing |
| `SpeakerPanel` | Encounter | idle, speaking, listening, scrollback |
| `LevelMeter` | Encounter, pre-flight | silent, active, clipping, reduced-motion static |
| `DirectionalCue` | Encounter | to-Spanish, to-English |
| `TranscriptStream` | Encounter, report | streaming, committed, empty, virtualised |
| `SourceRenderingDiff` | Turn review, report, trainer | clean, findings, multi-finding, ambiguous |
| `FindingCard` | Turn review, report, trainer | critical, non-critical, overridden |
| `CompetencyRadar` + `CompetencyBars` | Report, progress | data, sparse-data, empty, table-view |
| `SkillTrendChart` | Progress | data, single-point, empty, table-view |
| `ScenarioCard` | Library, picker | default, recommended, previously-attempted, locked |
| `PreflightStep` | Pre-flight | pending, checking, passed, failed |
| `ModeBadge` | Encounter, report | practice, assessment |
| `CoachCard` | Encounter (practice) | entering, visible, dismissed, capped |
| `ReviewQueueItem` | Trainer | pending, in-review, complete |
| `ConfidenceDisclosure` | Report | always visible, non-collapsible |

---

## 10. What the interface deliberately does not do

| Not doing | Why |
|---|---|
| Live scores during an encounter | Trains scoreboard-watching instead of interpreting |
| Streak counters, badges, leaderboards | Manufactures guilt; hostile to shift-working professionals; competition is wrong for a safety skill |
| A single overall grade | Collapses a multi-dimensional skill into a number that invites misuse as an employment signal |
| Auto-share to a trainer | The trainee owns their record; sharing is an explicit act |
| Hide the system's own error rate | An instrument that assesses people must disclose its measured accuracy alongside the assessment |
| Word-by-word streaming of the trainee's own speech | Delayed auditory feedback measurably disrupts production |
| Machine-translated interface strings | The users are language professionals; they will notice, and it undermines the product's credibility |
