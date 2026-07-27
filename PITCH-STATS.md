# Pitch stats — ready to paste into a devpost / deck

Every number here is sourced in [`docs/01-research.md`](docs/01-research.md). Pull the citation from there if a reviewer asks.

## The problem is real — clinical evidence

- **31 interpreter errors per encounter** on average; **63% carry potential clinical consequence.** *(Flores et al., Pediatrics, 2003)*
- **Omission is 52%** of all errors — the meaning doesn't get mangled, it silently disappears.
- Errors of potential clinical consequence: **12% with a professional interpreter, 22% with an ad hoc interpreter, 20% with none.** *(Flores et al., Annals of Emergency Medicine, 2012)*
- **The killer stat:** training *hours* — not years of experience — predict error rates. ≥100 hours of training → **2%** clinically consequential errors. Under 100 hours → **12%**. *(same study)*
- Replicated in adult primary care: ad hoc interpreters ran **~2x the inaccuracy rate** of professional interpreters (54% vs 23–25% of thought units). *(Nápoles et al., Med Care, 2015)*

## The gap is local and quantified — Santa Cruz County

- Santa Cruz County: **33.6%** speak a language other than English at home; **12.1%** LEP. *(Census ACS 2020–2024, derived from official counts)*
- **Watsonville specifically: 74.5%** language-other-than-English, **71.1%** Spanish, **32.4%** LEP. *(same source)*
- **PVUSD: 34.1%** of students (5,614 of 16,452) are English Learners. *(CA Dept. of Education, 2025–26)*
- **Salud Para La Gente** (the Watsonville safety-net clinic): **27,480 patients, 182,186 visits**; **71%** best served in a language other than English; **only 3 Mixteco interpreters.**
- **Watsonville Community Hospital employs zero Mixtec interpreters** — relies on a phone service.
- 12 Mixtec doulas completed training in 2025 and remain **blocked from working inside the hospital** on administrative grounds.

## Why nobody's solved this

- Certification-grade assessment is scored by **2+ trained human raters per response** — rigorous, and structurally impossible to scale to daily practice.
- Closest existing product (Knowi, $38/mo) publishes no rubric and no accuracy figures. Nothing found combines: known-source scoring, measured accuracy against human experts, and open reporting of that accuracy.

## The one-liner

*"Training hours — not experience — cut clinically dangerous interpreter errors from 12% to 2%. Training is scarce because certification-grade assessment needs two human raters per response. We built the tool that makes it unlimited — and we're built to publish exactly how our scoring agrees with human experts, because nobody else publishes that number."*

**Status note (not for the pitch deck, for whoever pastes from this file):** the measurement harness that produces that agreement number exists and is tested end-to-end — see `src/rehearsal/evals/`. The number itself does not exist yet: it requires 40 hand-labelled calibration turns per `misc/SETUP.md` §6, and no one has labelled them. Every accuracy cell is `—` until that happens (`misc/plans/metrics-snapshot.md`). Don't paste a past-tense "we proved X" claim from this stat sheet — say "the tool is built to prove it" until the labels exist.
