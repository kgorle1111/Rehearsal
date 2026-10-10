# Rehearsal

> **Status: archived (October 2026). Text-mode prototype, no longer maintained.**
>
> **What works:** a text-mode scoring pipeline for interpreter renditions. Rule-based checks for dosages, laterality, allergies (including allergic / not-allergic polarity) and frequency catch planted errors. 288 tests pass, with strict mypy and ruff clean.
>
> **Not built:** voice. There is no speech-to-text, audio I/O, VAD or TTS; the system is text-only. Clinician and patient agents run on scripted templates or a local Ollama model. See [`NOT-BUILT-YET.md`](NOT-BUILT-YET.md).
>
> **Known limits:**
> - The negation and number extractors exist but aren't wired into scoring, so a dropped "no" or "not" isn't flagged.
> - Compound spelled-out numbers aren't parsed ("twenty-five" reads as 20 and 5; "two hundred" as 2).
> - The evals EV-01 to EV-03 are blocked until a human labels a calibration set.
>
> The description below is the original design; much of it (voice loop, real-time latency, calibrated scores) was never built.
>
> **Setup:** [`misc/SETUP.md`](misc/SETUP.md) §2 installs it; then `make test` (or `uv run pytest`). Most other `make` targets named in SETUP.md (`models`, `scenarios`, `dev`, `session`, `calibrate`) don't exist in the Makefile. **License:** MIT, see [`LICENSE`](LICENSE).

**A local, voice-based training and assessment system for medical interpreters and bilingual community health workers.**

A trainee stands in the middle of a simulated clinical encounter. An AI clinician speaks English. An AI patient speaks Spanish. The trainee interprets aloud between them, exactly as they would in a real triadic encounter. Afterwards, the system shows what meaning survived each interpretation and what did not — omissions, additions, substitutions, distortions — scored against an error taxonomy drawn from the interpreting research literature and aligned to the NCIHC Standards of Practice, with the clinically dangerous errors checked deterministically rather than judged.

Everything runs on local open models. No audio, transcript or performance record leaves the machine.

---

## The problem

Interpreting errors in clinical encounters are frequent and consequential, and the evidence on what fixes them is unusually specific.

- **31 interpreter errors per encounter** on average, **63% carrying potential clinical consequence** (Flores et al., *Pediatrics*, 2003).
- **Omission accounts for 52%** of those errors — content that silently disappears, which is the hardest failure to notice without a reference to compare against.
- Errors of potential clinical consequence: **12% with a professional interpreter, 22% with an ad hoc interpreter, 20% with none** (Flores et al., *Annals of Emergency Medicine*, 2012).
- **Training hours — not years of experience — predict error rates.** Interpreters with ≥100 hours of training: median 12 errors, **2%** clinically consequential. Under 100 hours: median 33 errors, **12%** consequential (same study).

That last finding is the product's reason to exist. The variable that reduces clinical harm is *training volume*, and training volume is exactly what is scarce: certification-grade assessment is human-rated by two or more trained raters per response, which makes it rigorous and makes daily practice impossible.

Locally, the constraint is concrete. Salud Para La Gente, the Watsonville federally qualified health centre, served **27,480 patients across 182,186 visits** in its most recently published annual report; **71% are best served in a language other than English** — and the organisation reports access to **three Mixteco interpreters**. Watsonville Community Hospital employs **none**, relying on a telephone service.

Full evidence, with sources, dates and honestly-stated gaps: [`docs/01-research.md`](docs/01-research.md).

---

## What makes it work

**Ground truth by construction.** The system generates the source utterance, so it knows exactly what was said. Scoring is therefore *"compare a known sentence to the trainee's rendering"* — a tractable, defensible problem — rather than *"judge whether this was good," which has no ground truth and produces confident nonsense.

**Deterministic where it matters.** Numbers, dosages, frequencies, negation, laterality and allergies are checked by symbolic extractors, not by a language model. These are exactly the categories the clinical literature identifies as consequential, and they are provably decidable. The model handles only the semantic residue — register, idiom, pragmatic force.

**Measured against humans.** The scorer's agreement with hand-labelled expert judgement is measured on a sealed test split and reported alongside the human ceiling (how well human raters agree with each other). A score is only worth acting on if you know how often it is right.

**Isolated agents.** The clinician and patient agents never see the scoring rubric. If they did, they would unconsciously speak in easy-to-interpret ways and quietly destroy the training's realism. This is verified by a leakage A/B test, not asserted.

**Off the critical path.** Scoring runs while the trainee is still speaking. The human's own speaking time is the latency budget — which is what makes a multi-model real-time voice loop feasible on one machine.

---

## Documentation

| Document | Contents |
|---|---|
| [`misc/SETUP.md`](misc/SETUP.md) | Everything needed to run the system — prerequisites, models, data, and **the calibration protocol (§6)** that anchors every number the project reports |
| [`misc/docs/00-dossier.md`](misc/docs/00-dossier.md) | The product: problem, users, thesis, scope, and what it deliberately is not |
| [`docs/01-research.md`](docs/01-research.md) | Evidence base — clinical literature, professional standards, local context, prior art, and named gaps |
| [`misc/docs/02-layer-vertical.md`](misc/docs/02-layer-vertical.md) | The capability vertical: what is built at each layer and the eval that proves it was earned |
| [`misc/docs/03-system-architecture.md`](misc/docs/03-system-architecture.md) | End-to-end architecture, components, trust boundaries, session state machine |
| [`misc/docs/04-ai-engineering.md`](misc/docs/04-ai-engineering.md) | Agent roster, information isolation, context discipline, prompt optimisation |
| [`misc/docs/05-voice-pipeline.md`](misc/docs/05-voice-pipeline.md) | Real-time audio: latency budget, barge-in, turn-taking, memory layout, degradation ladder |
| [`misc/docs/06-scoring-engine.md`](misc/docs/06-scoring-engine.md) | The fidelity scorer — symbolic extractors, semantic pass, merge logic, worked examples |
| [`misc/docs/07-data-and-scenarios.md`](misc/docs/07-data-and-scenarios.md) | Clinical state graph, scenario bank, corpus requirements, retention |
| [`misc/docs/08-evals.md`](misc/docs/08-evals.md) | The measurement system — every metric, gate, and what the evals cannot tell you |
| [`misc/docs/09-ui-ux.md`](misc/docs/09-ui-ux.md) | Complete interface and experience design |
| [`misc/docs/10-frontend-spec.md`](misc/docs/10-frontend-spec.md) | Frontend implementation contract, design tokens, accessibility |
| [`misc/docs/11-backend-api.md`](misc/docs/11-backend-api.md) | API surface, real-time protocol, data model |
| [`misc/docs/12-security-privacy.md`](misc/docs/12-security-privacy.md) | Threat model, data inventory, responsible-use position |
| [`misc/docs/13-deployment-ops.md`](misc/docs/13-deployment-ops.md) | Packaging, release gates, observability without telemetry, runbooks |
| [`misc/docs/14-testing-strategy.md`](misc/docs/14-testing-strategy.md) | Software correctness — distinct from model quality in `08-evals.md` |
| [`misc/docs/15-workstreams.md`](misc/docs/15-workstreams.md) | Parallel workstreams, file ownership, frozen interface contracts |
| [`misc/docs/16-roadmap.md`](misc/docs/16-roadmap.md) | Stages defined by evidence and dependency |
| [`misc/docs/17-decisions.md`](misc/docs/17-decisions.md) | Decision record — every consequential choice and its price |
| [`misc/docs/18-glossary.md`](misc/docs/18-glossary.md) | Interpreting, clinical and system vocabulary |
| [`misc/MODEL_CARD.md`](misc/MODEL_CARD.md) | Models used, intended use, prohibited use, limitations, bias |
| [`misc/DATA_CARD.md`](misc/DATA_CARD.md) | Every data asset: provenance, sensitivity, retention |
| [`misc/CONTRIBUTING.md`](misc/CONTRIBUTING.md) · [`misc/SECURITY.md`](misc/SECURITY.md) · [`misc/CHANGELOG.md`](misc/CHANGELOG.md) | Contribution, disclosure, release discipline |

---

## Principles

These govern every document and every line of code. A change that violates one is wrong by definition, not by preference.

1. **The model generates and extracts. Deterministic code decides anything consequential. The human decides ultimately.**
2. **Ground truth by construction** — never ask a model to judge what can be checked.
3. **Every layer ships an eval number.** Design arguments are settled with measurements, not philosophy.
4. **Honest reporting.** Rates and uncertainty, never false precision. Named gaps, never smoothed ones. No capability claim without a measurement behind it.
5. **The trainee owns their record.** Performance data is a formative training signal, not employment evidence.
6. **Local by default.** Nothing is transmitted.

---

## Living documents

`plans/` (git-ignored) holds internal working material, including `metrics-snapshot.md` — the single place current numbers live.

**When an eval run produces a number that differs materially from the snapshot, update the snapshot in the same session, then correct anything downstream that the new number invalidates.** `make evals` diffs against the snapshot and prints a reminder. A number that changes in the test output but not in the material derived from it is how a project ends up asserting something its own repository contradicts.

---

## Status

Early. The architecture, evaluation design and interface are specified; the calibration anchor described in [`misc/SETUP.md`](misc/SETUP.md) §6 is the gating prerequisite for any performance claim. No performance numbers are published in this repository until that calibration exists and is measured on a sealed split.

## Licence

MIT. See [`LICENSE`](LICENSE).
