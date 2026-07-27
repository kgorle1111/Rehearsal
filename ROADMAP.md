# Roadmap

What runs today vs. what's deferred. Detailed per-phase deferral notes stay in
`NOT-BUILT-YET.md`; this is the ordered "later" list.

## Works NOW (the demo)

Text-mode end-to-end session, fully local:

```bash
uv run rehearsal review        # one-time: human-approve the seed scenarios
uv run rehearsal demo          # patient speaks Spanish (Gemma via Ollama),
                               # you type English, scorer + coach respond
```

Verified working: Gemma 4 E4B (Ollama, local) generates in-character Spanish
patient turns from scenario facts; the neuro-symbolic scorer catches
deterministic criticals (frequency, negation, allergy, laterality, dosage,
numbers, entities) via extractors and semantic issues via a single structured
grader call to the same local model; the coach emits one hint per turn; a
session summary closes it out.

## Later — ordered by value

1. **Voice loop** (the headline feature): real audio I/O, VAD/endpointing,
   TTS, barge-in. The FSM, chunker, endpoint policy, and budget guard are
   built and tested against fakes — this is wiring real audio into existing
   seams, not new architecture.
2. **API + frontend**: FastAPI app and the vanilla-TS frontend exist
   (uncommitted, untested against a live backend). Wire WS transport to the
   orchestrator loop, then the browser UI replaces the CLI.
3. **Two-model layout**: separate live/grader model processes with GPU
   admission control, so grading runs off the critical path. One Ollama model
   serves both seams today.
4. **Manifest-anchored scoring**: extractors compare against the scenario's
   term manifest (true ground-truth-by-construction) instead of
   source-text-vs-rendering; unlocks grader-critical findings in merge.
5. **Calibration + evals** (blocked on human labels): the 40-item bank is
   authored (`data/calibration/`), labeling tools are built (`tools/`);
   label it, then WS9 evals + WS6 prompt optimisation produce real numbers.
6. **Scenario graph traversal**: replace the demo's fixed
   timeline→meds→allergies node plan with real `ClinicalStateGraph` paths.
7. **Temporal extractor**: currently absent; temporal grader findings stay
   capped non-critical until it ships.
8. **Store/persistence wiring**: SQLite event store exists (uncommitted);
   demo sessions aren't persisted yet.
