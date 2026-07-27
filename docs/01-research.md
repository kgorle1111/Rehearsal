# 01 — Research & Evidence Base

## How to read this document

Every claim below carries a source and a date. Confidence is marked explicitly:

- **VERIFIED** — traced to a primary source (peer-reviewed paper, standards body publication, or an organisation's own published report) and read directly.
- **DERIVED** — computed by arithmetic on official counts from a primary source (e.g. a percentage calculated from raw ACS table counts, when the source's own pre-built percentage table could not be accessed). The underlying counts are primary; the percentage itself is our calculation, not a source-stated figure.
- **ESTIMATE** — a figure published by a credible organisation but derived or self-characterised rather than measured.
- **UNVERIFIED** — encountered but not independently confirmed. Treated as a lead, never as a fact.

Section 8 lists what could **not** be verified. Those gaps are stated plainly rather than smoothed over; several of them are material, and one of them changes how the product describes its own rubric.

---

## 1. Why interpreting fidelity matters — the clinical evidence

This is the evidentiary foundation of the entire product. It is unusually strong: the effect is measured, replicated across decades and settings, and the mechanism is specific.

### 1.1 Errors are frequent and consequential

**VERIFIED.** In audio-taped paediatric outpatient encounters using Spanish interpreters, **396 interpreter errors** were recorded across 13 encounters — a mean of **31 errors per encounter** — of which **63% had potential clinical consequence** (mean 19 per encounter).
*Flores G, Laws MB, Mayo SJ, et al. "Errors in medical interpretation and their potential clinical consequences in pediatric encounters." Pediatrics 2003;111(1):6–14.* [PubMed](https://pubmed.ncbi.nlm.nih.gov/12509547/)

**VERIFIED.** Documented consequential errors in that study included omitting questions about **drug allergies** and omitting **antibiotic dose, frequency and duration** — precisely the categories this system treats as deterministically checkable critical errors (see `docs/06-scoring-engine.md`).

**VERIFIED.** The distribution of error types in the 2003 study:

| Error type | Share of errors |
|---|---|
| Omission | 52% |
| False fluency | 16% |
| Substitution | 13% |
| Editorialization | 10% |
| Addition | 8% |

*Same source.* **Omission is by far the dominant failure mode** — a fact that directly shapes the scoring engine, which must detect *absent* content, not merely wrong content.

### 1.2 Professional training changes outcomes

**VERIFIED.** The 2012 follow-up analysed **57 audio-taped paediatric emergency encounters** (20 professional interpreter, 27 ad hoc, 10 no interpreter), coding **1,884 errors**, of which **18%** had potential clinical consequence. The headline comparison:

| Interpreter type | Errors of potential clinical consequence |
|---|---|
| Professional interpreter | **12%** |
| Ad hoc interpreter | **22%** |
| No interpreter | **20%** |

*Flores G, Abreu M, Barone CP, Bachur R, Lin H. "Errors of Medical Interpretation and Their Potential Clinical Consequences: A Comparison of Professional Versus Ad Hoc Versus No Interpreters." Ann Emerg Med 2012;60(5):545–553.* [PubMed](https://pubmed.ncbi.nlm.nih.gov/22424655/)

**VERIFIED — and this is the single most important finding for this product.** Among professional interpreters, **hours of prior training — not years of experience — predicted error rates**:

| Training | Median errors | Errors of potential consequence |
|---|---|---|
| ≥100 hours of training | 12 | **2%** |
| <100 hours of training | 33 | **12%** |

*Same source.* The implication is direct: **the intervention that reduces clinically consequential interpreting error is training volume.** A system that makes high-quality, measured practice available in unlimited quantity is attacking the variable the evidence identifies as causal, not a proxy for it.

**VERIFIED.** Replicated in adult primary care: in 32 audio-recorded encounters with Spanish-speaking Latino patients, **871 interpretation errors** were coded (~27 per visit); **30% of coded thought units** were inaccurate, and 7.1% were moderately or highly clinically relevant. Inaccuracy roughly doubled with ad hoc interpreters (**54%** of thought units) versus professional in-person (**25%**) or videoconference (**23%**).
*Nápoles AM, Santoyo-Olsson J, Karliner LS, et al. Med Care 2015;53(11):940–947.* [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC4610127/)

### 1.3 What this establishes

1. Interpreting errors are frequent, and a large minority carry clinical consequence.
2. Omission dominates — the hardest error class to notice without a reference to compare against.
3. Training volume, specifically, separates low-error from high-error professional interpreters.
4. The error categories that matter clinically (dosage, frequency, duration, allergy) are exactly the categories that can be checked deterministically rather than judged subjectively.

---

## 2. Professional standards and the error taxonomy

### 2.1 The authoritative standards

**VERIFIED.** The **NCIHC National Code of Ethics for Interpreters in Health Care** (July 2004) establishes **nine ethical principles**, including confidentiality, accuracy, impartiality and role boundaries. Principle 2 requires the interpreter to *"strive to render the message accurately, conveying the content and spirit of the original message."*
[NCIHC National Code of Ethics (PDF)](https://www.ncihc.org/assets/documents/publications/NCIHC%20National%20Code%20of%20Ethics.pdf)

**VERIFIED.** The **NCIHC National Standards of Practice for Interpreters in Health Care** (September 2005) contains **32 standards under nine headings** (Accuracy, Confidentiality, Impartiality, Respect, Cultural Awareness, Role Boundaries, Professionalism, Professional Development, Advocacy).
[NCIHC National Standards of Practice (PDF)](https://www.ncihc.org/assets/Accessible-files/NCIHC%20National%20Standards%20of%20Practice%20Sept%202005.pdf)

The standards that map directly onto this system's scoring:

| Standard | Content | Maps to |
|---|---|---|
| **Standard 1** | *"The interpreter renders all messages accurately and completely, without adding, omitting, or substituting."* | The omission / addition / substitution triad — the canonical professional statement |
| **Standard 2** | *"The interpreter replicates the register, style, and tone of the speaker."* | `register_shift` |
| **Standards 5–6** | The interpreter corrects errors in interpretation and maintains transparency | Self-correction handling (see §8 gap) |
| **Standards 16–18** | Role boundaries — the interpreter limits activity to interpreting | `role_exchange` |
| **Standard 12** | Nearest provision to first-person practice | `first_person_violation` — **see the gap in §8.1** |

**VERIFIED.** NCIHC defines *register* in its glossary as *"a stylistic level of language used by a speaker,"* adapted to topic, parties addressed and perceived formality — the definition this system's `register_shift` finding is written against.

### 2.2 How the profession itself assesses fidelity

**VERIFIED.** The **CCHI** CHI oral performance exam — a leading US healthcare-interpreter credential — is scored **entirely by trained human raters**: 7 scored vignettes, **two independent raters per response** (up to 14 raters per candidate), with a third rater on disagreement.
[CCHI — CHI Exam Score](https://cchicertification.org/certifications/preparing/chi-score/)

**VERIFIED.** The **NBCMI** CMI oral exam is likewise human-rated, scored on linguistic equivalence, conservation of register, grammatical correctness and pronunciation, with reported **inter-rater reliability of .98 (N=59)** and 210 scoring units per pilot form.
*PSI Services LLC, "Development and Validation of Oral and Written Medical Interpreter Examinations," April 2010.* [Technical report (PDF)](https://nbcmi.memberclicks.net/assets/docs/oral-and-written-medical-interpreter-technical-report.pdf)

Two consequences for this project:

1. **Human rating is the professional standard of truth.** This is why the calibration set (`SETUP.md` §6) is anchored to human labels and why inter-rater agreement is the ceiling this system is measured against — not an arbitrary target.
2. **The profession's own reliability benchmark is high** (.98 inter-rater on a heavily-engineered exam with trained raters). This system does not claim to match a certification instrument, and should never be described as one. See `MODEL_CARD.md` for the out-of-scope statement.

---

## 3. The local context: Santa Cruz County

The population this product is built for is concentrated, documented, and underserved in a specific, measurable way.

### 3.0 Census language demographics

**VERIFIED.** Santa Cruz County's total population is **262,406** (Census Bureau Vintage 2024 estimate). The American Community Survey 2020–2024 5-year sample (a different vintage/methodology — do not conflate the two figures) covers a population aged 5+ of **253,284**.
[Census QuickFacts, Santa Cruz County](https://www.census.gov/quickfacts/fact/table/santacruzcountycalifornia/PST045224)

**DERIVED, from ACS table C16001 (2020–2024 5-year estimates).** The Census Bureau's own pre-built percentage table (S1601) could not be retrieved directly (it renders client-side); the figures below are calculated from the table's raw counts, which are official ACS data:

| Measure | Count | Share of population 5+ |
|---|---|---|
| Speaks a language other than English at home | 85,033 | **33.6%** |
| Limited English Proficient (speaks English less than "very well") | 30,708 | **12.1%** |
| Speaks Spanish at home | 66,838 | **26.4%** |
| Speaks Spanish at home *and* LEP | 25,962 | **10.3%** |

*Source table: ACS 2020–2024 5-Year Estimates, C16001, geography 05000US06087 (Santa Cruz County). Counts confirmed via the Census Bureau API mirror at [Census Reporter](https://api.censusreporter.org/1.0/data/show/latest?table_ids=C16001&geo_ids=05000US06087).*

**DERIVED, same table and method, for the City of Watsonville** (geography 16000US0683668) — the population centre of the Pajaro Valley:

| Measure | Count | Share of population 5+ |
|---|---|---|
| Total population 5+ | 48,578 | — |
| Speaks a language other than English at home | 36,170 | **74.5%** |
| Speaks Spanish at home | 34,560 | **71.1%** |
| Limited English Proficient (all languages) | 15,752 | **32.4%** |

This confirms and sharpens the Salud Para La Gente figures in §3.1 with an independent, official source: roughly three-quarters of Watsonville residents speak a language other than English at home, and roughly a third are LEP.

**VERIFIED.** In Pajaro Valley Unified School District, **34.1% of enrollment (5,614 of 16,452 students) are classified English Learners**, 2025–26 school year.
[California Dept. of Education, School District Profile, PVUSD](https://www.cde.ca.gov/sdprofile/details.aspx?cds=44697990000000)

**Indigenous Mexican languages (Mixteco, Triqui, Zapoteco) — NOT FOUND, and this is a genuine data gap, not a search failure.** Census/ACS language tables have no category for Mesoamerican indigenous languages at county or city geography; respondents speaking these languages are absorbed into "Spanish" or "other Indo-European languages" depending on self-report, and the Bureau publishes no breakout that separates them. **No number should be stated for this population from Census data.** The only concrete figures available for this population are the provider-reported ones in §3.2 (Salud Para La Gente's 6–10% estimate; Watsonville Community Hospital's interpreter count) — organisational characterisations, not census measurements, and already marked as such.

### 3.1 The primary safety-net provider

**VERIFIED.** **Salud Para La Gente**, the federally qualified health centre serving Watsonville and South Santa Cruz County, served **27,480 patients across 182,186 visits in 2024**, from 13 service sites (7 clinics, 3 school-based, and others).
*Salud Para La Gente, 2024 Impact Report (published March 2025).* [PDF](https://splg.org/flyer/2024_IMPACT_REPORT.pdf)

**VERIFIED.** **71% of its patients are best served in a language other than English.** 92% identify as Hispanic/Latino; 73% are Medi-Cal enrolled. Its OB/GYN service delivered **591 babies** in 2024.
*Same source.*

### 3.2 The interpreter capacity gap — stated by the providers themselves

**VERIFIED.** Salud Para La Gente reports access to **only three Mixteco interpreters**, and rolled out video interpreting across its clinics in 2024 specifically to address language-access gaps.
*Same source.*

**ESTIMATE.** Salud Para La Gente characterises its service area as one where **6–10% speak Indigenous languages** (primarily Mixteco and Triqui) in addition to the 71% best served in a language other than English.
*Same source — organisational characterisation, not a measured census figure.*

**VERIFIED.** **Watsonville Community Hospital employs no Mixtec interpreters**, relying instead on an over-the-phone interpretation service.
*Santa Cruz Local, "Watsonville hospital seeks to add Mixtec doulas, but challenges remain," 19 September 2025.* [Article](https://santacruzlocal.org/2025/09/19/watsonville-hospital-seeks-to-add-mixtec-doulas-but-challenges-remain/)

**VERIFIED.** Twelve Mixtec women farmworkers completed a four-day doula training under Campesina Womb Justice, intended to place Mixteco-speaking support inside the hospital. The programme is **blocked from operating inside the hospital by mandated background-check requirements**. The precursor Spanish-language volunteer doula programme had only **two regular volunteers**.
*Same source.*

### 3.3 What the local picture establishes

A population where roughly three in four patients need language support, served by an interpreter workforce measured in single digits for its Indigenous-language communities, with a documented, currently-blocked community effort to expand that workforce. The constraint is not awareness or willingness — it is **trained, available interpreting capacity**. That is the constraint a scalable training instrument addresses.

---

## 4. The competitive and prior-art picture

**VERIFIED.** **Exec.com's "Medical Interpreter AI Roleplay Training"** is a marketing page for a general-purpose AI roleplay platform ("AI roleplays, call scoring, and live coaching" with customer-configurable evaluation criteria) — not a purpose-built interpreting instrument. It publishes no rubric, no technical description, and no validation.
[Exec.com page](https://www.exec.com/learn/medical-interpreters-ai-roleplay-training) (page last updated December 2025)

**VERIFIED.** The closest commercial product performing automated grading of interpreting practice is **Knowi** (Southern California School of Interpretation): AI-generated and AI-graded practice sessions, **$38/month, five AI-generated and five AI-graded practices, Spanish/English only**.
[Interpreting.com — AI Practice Tools](https://interpreting.com/For-Interpreters/AI-for-Interpreters.html)

**VERIFIED.** **Language Testing International** (the ACTFL testing office) sells language *proficiency* assessments (OPI, OPIc, LPT, RPT, WPT) scored by ACTFL-certified human raters — proficiency, not interpreting fidelity.
[LTI — Language Testing for Interpreters](https://www.languagetesting.com/blog/interpreter-language-testing/)

**UNVERIFIED.** ALTA Language Services offers phone-delivered interpretation and Qualified Bilingual Staff assessments (~$140–160 per assessment, 100+ languages). InterpreMed provides practice audio, glossaries and note-taking drills as a practice community. A University of Wisconsin pilot built high-fidelity simulation training for medical interpreters — **human-assessed**.
*Sources: [ALTA](https://altalang.com/language-testing/interpretation-practice-test/); [InterpreMed](https://interpremed.com/); [PEC Innovation, September 2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC10550806/)*

### 4.1 The surviving gap

Practice material exists. Human-rated certification exists, and is rigorous. Generic AI roleplay platforms exist. One low-cost AI-graded practice product exists, with an unpublished rubric.

**What does not exist, as far as this research could establish: a system that scores interpreting fidelity against a documented interpreting error taxonomy, using a known source utterance as ground truth, with its own scoring accuracy measured against human expert labels and reported publicly.**

That last clause is the real gap. Knowi grades; it does not publish what its grader measures or how accurate it is. The certification bodies measure accuracy rigorously but do so with human raters at a cost and scale that makes daily practice impossible. This system's contribution is not "AI can grade interpreting" — it is **grading with a stated, measured, publicly-reported agreement against human expert judgement**, which is what makes a score worth acting on.

---

## 5. What this means for the product

| Evidence | Design consequence |
|---|---|
| Omission is 52% of errors | The scorer must detect *absent* content — this is why comparison against a known source is architecturally necessary, not a convenience |
| Dosage/frequency/allergy omissions are the documented consequential errors | These become the deterministically-checked **critical** class (`docs/06-scoring-engine.md`) |
| Training hours predict error rate; experience does not | Unlimited measured practice is the intervention; volume is the mechanism |
| Ad hoc interpreters roughly double consequential error rates | Bilingual staff and promotoras pressed into interpreting are the highest-leverage population to train |
| Certification is human-rated with ~.98 inter-rater reliability | Human labels are the ground truth; the system reports agreement against them and never claims certification-grade authority |
| Salud: 71% non-English-preferred, 3 Mixteco interpreters | The capacity constraint is real, local, and quantified |

---

## 6. Datasets

**NOT COMPLETED.** The dataset survey did not finish. `docs/07-data-and-scenarios.md` specifies the *requirements* a corpus must meet (licence, PHI status, de-identification, suitability for scenario seeding). Before any corpus is ingested, this section must be completed with, per dataset: name, host, URL, size, licence, redistribution terms, PHI/de-identification status, and intended use.

Constraint that already holds regardless of which corpora are chosen: **public clinical corpora ground *realism*, never *truth*.** Ground truth in this system comes from construction — the system generates the source utterance and therefore knows it exactly.

---

## 7. Workforce and policy environment

### 7.1 The interpreter workforce

**VERIFIED, national only.** For "Interpreters and Translators" (BLS occupational classification): approximately **75,300 jobs** (2024 baseline), median annual wage **$59,440** (May 2024), projected growth **2% from 2024–2034** — slower than the average occupation — with roughly 6,900 annual openings, most from workforce replacement rather than growth.
[BLS Occupational Outlook Handbook, Interpreters and Translators](https://www.bls.gov/ooh/media-and-communication/interpreters-and-translators.htm) — **held with moderate confidence**: the figures were retrieved via search rather than a direct, independently timestamped fetch of the live BLS page. Re-verify before citing in an external publication.

**NOT FOUND.** A California-specific BLS state/MSA breakout for this occupation (available at [BLS OEWS](https://www.bls.gov/oes/current/oes273091.htm), not retrieved in this pass).

### 7.2 California's Medi-Cal Community Health Worker benefit — and why it does not cover interpreting

**VERIFIED.** The Medi-Cal CHW benefit became effective **1 July 2022**. Certification requires either (a) completion of a CHW training programme covering communication, service coordination, navigation, advocacy and education/facilitation, or (b) 2,000+ hours of paid or volunteer experience within 3 years, with certification completed within 18 months of first billing, plus 6 hours/year of continuing training. Billing runs through CPT 98960, with HCPCS G0019/G0022 added **1 April 2025** for acute, social-determinants-focused CHW work.
[DHCS — Community Health Workers](https://www.dhcs.ca.gov/community-health-workers) · [DHCS CHW Provider Requirements FAQ](https://www.dhcs.ca.gov/providers-partners/frequently-asked-questions-for-medi-cal-community-health-worker-services-provider-requirements/) · [DHCS CHW Billing FAQ](https://www.dhcs.ca.gov/providers-partners/faqs-for-medi-cal-community-health-worker-services-billing/)

**VERIFIED — the structural finding that matters most for this product: medical interpreting and the CHW benefit are separate regulatory and financial tracks, and should never be conflated in product messaging.** CHW scope is preventive and navigational work (chronic disease management, behavioural health, social determinants); a CHW may *connect* a member to interpretation resources but does not bill as an interpreter under this benefit. Medical interpreting in California managed care is governed independently under **California Code of Regulations, Title 28, §1300.67.04** (the Health Care Language Assistance Program regulations), which mandates 24/7 no-cost oral interpretation at all points of contact plus written translation in DHCS-designated threshold languages (≥3,000 speakers, or ≥5% of a plan's enrollment).
[CCR Title 28 §1300.67.04](https://regulations.justia.com/states/california/title-28/division-1/chapter-2/article-7/section-1300-67-04/)

*Confidence: moderate.* This is inferred from DHCS's CHW scope description plus the existence of the parallel §1300.67.04 track, not from an explicit "interpreting is excluded from CHW scope" clause quoted from the primary provider manual. For an airtight citation, pull the covered-services list directly from the [DHCS CHW Medi-Cal Provider Manual](https://www.providerservices.iehp.org/content/dam/provider-services-rd/en/documents/providers/programs/community-health-worker-benefit/DHCS%20Community%20Health%20Worker%20Medi-Cal%20Provider%20Manual.pdf).

### 7.3 Federal language-access obligations

**VERIFIED.** Title VI of the Civil Rights Act (1964) and Section 1557 of the Affordable Care Act jointly prohibit national-origin discrimination, which HHS Office for Civil Rights interprets as requiring language access for LEP patients at virtually all providers accepting federal funds, Medicare or Medicaid. HHS finalised a new Section 1557 rule in **April/May 2024** requiring language services from *qualified* interpreters and translators (a defined competency standard — not simply any bilingual staff member), provided free of charge, in a timely manner, and confidentially, plus a "Notice of Availability" of language assistance in English and the 15 most common LEP languages in the state.
[National Health Law Program, Title VI & Section 1557 explainer, updated December 2025](https://healthlaw.org/wp-content/uploads/2024/05/2025_12_11_T-VI-and-Sec-1557-explainer-2025-update.pdf)

**VERIFIED, narrow scope.** The rule's *gender-identity* provisions were stayed by courts and the underlying 2021 interpretive guidance was rescinded by HHS on **14 May 2025**, as part of a broader deregulatory action.
[Morgan Lewis, "HHS Rescinds Prior Section 1557 Guidance," June 2025](https://www.morganlewis.com/pubs/2025/06/on-the-basis-of-sex-hhs-rescinds-prior-section-1557-guidance-interpreting-sex-based-discrimination)

**ESTIMATE — not directly verified.** No source was found affirmatively confirming that the *language-access* provisions (qualified-interpreter standard, Notice of Availability) survived the 2025 deregulatory action intact. Nothing found suggests they were stayed or rescinded, but their current enforcement status was not independently confirmed as of this research. **Do not state that these provisions are "in force" without a fresh, direct check** — the 2025 rescission activity specifically targeted the rule's gender-identity provisions, and the research here traced that thread, not a full re-confirmation of the language-access sections.

### 7.4 Cost of professional interpreting to providers

**NOT FOUND.** No primary-source, provider-facing vendor pricing (a published rate card from a language-services company, e.g. per-hour or per-minute billing) was located. What surfaced instead was **interpreter employee wage data** — a different figure (labour cost, not vendor billing rate) — ranging $21–50/hr across several salary-aggregator sites (Salary.com, ZipRecruiter, Glassdoor, PayScale). These are secondary, self-reported, rolling-average figures and **should not be substituted for vendor pricing** in any cost or market-sizing claim. An authoritative figure would require a direct quote or RFP response from a language-services company, or a paywalled industry report (CSA Research, ALC). This remains an open gap.

### 7.5 Standing rule

Every figure above carries its confidence level for a reason: §7.1's national wage/growth data is solid but state-level detail is missing; §7.2 establishes a structural fact (CHW ≠ interpreting) with moderate confidence in its exact regulatory citation; §7.3's core language-access requirement is well-sourced but its 2025–2026 survival was not independently reconfirmed; §7.4 is a genuine, unfilled gap. Nothing here should be cited in `plans/writeup-plan.md`, `plans/video-plan.md`, or any external communication above the confidence level stated.

---

## 8. Named gaps and unresolved issues

### 8.1 The taxonomy has no single authoritative source — and this changes how we describe it

**This is the most important gap in this document.** Research established that:

- **No single authoritative publication defines the five/six-category research taxonomy as one unit, and the **nine** categories Rehearsal implements (`docs/06-scoring-engine.md` §3) are a further operationalisation of it.** The categories in common use derive from *research coding schemes* — principally Flores et al. and Vasquez & Javier (1991) — **not** from professional standards or certification rubrics.
- The NCIHC National Standards of Practice **contain no explicit first-person interpreting requirement.** The nearest provision is Standard 12. First-person practice is near-universal professional convention and is taught as such, but it is not stated as a standard in the way `first_person_violation` implies.
- "Condensation," the fifth category in Vasquez & Javier (1991), is commonly dropped from the modern five/six-category presentation without explanation.
- **No published, inter-rater-calibrated scoring rubric with operational decision rules for severity exists.** The certification bodies hold theirs internally.

**Required consequence for the product:** the taxonomy must be described as *"an operationalisation drawn from the research literature (Flores et al.; Vasquez & Javier) and aligned to NCIHC Standards of Practice 1, 2, 5–6, 12 and 16–18"* — not as "the professional standard taxonomy." Any document, interface string or report that implies the taxonomy is a single codified standard is overstating it. `docs/06-scoring-engine.md` and `MODEL_CARD.md` must carry this qualification. The absence of a public calibrated severity rubric is also, incidentally, part of what makes this project's own published calibration data a genuine contribution.

### 8.2 Other unverified or missing items

| Gap | Status |
|---|---|
| California-specific BLS interpreter workforce/wage breakout (§7.1) | National figures verified; state-level OEWS table not retrieved |
| Section 1557 language-access provisions' post-2025 enforcement status (§7.3) | Core requirement well-sourced; 2025–2026 survival not independently reconfirmed — do not assert "currently in force" without a fresh check |
| Vendor pricing for professional interpreting services (§7.4) | **Not found.** No primary-source rate card located; employee wage data exists but must not be substituted for vendor billing rates |
| Public datasets for scenario-bank seeding (§6) | **Research did not complete.** Corpus name, licence, PHI status and redistribution terms must be established per dataset before ingestion |
| HRSA UDS official data for Santa Cruz County FQHCs | Could not be retrieved; Salud's own published report is used instead |
| Santa Cruz Community Health language data | Organisation publishes none |
| County of Santa Cruz Health Centers language data | Not published |
| Watsonville Community Hospital patient language composition | Not published |
| The Willie Ramirez "intoxicado" case and its widely-quoted malpractice settlement figure | **Unverified — do not cite.** Widely repeated, not independently confirmed here |
| Divi et al. 2007 adverse-event denominators | Unverified |
| Current national LEP population size | Unverified; the AHRQ figure encountered (~25 million, 8.6%) is dated |
| Joint Commission Quick Safety 13 claims (longer stays, surgical infections, falls) | Unverified |
| Knowi's grading rubric and accuracy | Not published; could not be assessed |
| TalkTrack (MDPI Applied Sciences 16(14):7086) | Fetch returned HTTP 403; contents unassessed |
| Han & Lu 2025, "Beyond BLEU" — correlation coefficients between automatic metrics and human interpreting assessment | Could not obtain the actual figures |

### 8.3 Standing rule

No figure from §8 enters a document, an interface string, a report, or any external communication until it has been traced to a primary source and moved into the verified sections above. A gap stated honestly costs nothing; a confident number that turns out to be folklore costs the project its credibility on everything else.
