# 05 — Real-Time Voice Pipeline

The hardest engineering surface in Rehearsal. Everything else in the system can take an extra
200 ms and no one notices. Here, 200 ms is the difference between a clinical encounter and a
walkie-talkie.

This document owns the audio path from microphone to speaker: device handling, voice activity
detection, endpointing, barge-in, streaming and speculative TTS, GPU scheduling against the
off-path grader, the memory layout that makes concurrent models fit, the voice-specific
degradation triggers, and the per-turn timing record.

| Not owned here | Lives in |
|---|---|
| Session state machine, event log schema, seeds, replay | `docs/03-system-architecture.md` |
| Extractors, grader prompt, verdict merge, `heard_verbatim` handling downstream | `docs/06-scoring-engine.md` |
| Clinical state graph, scenario authoring, term manifests | `docs/07-data-and-scenarios.md` |
| Latency eval protocol, reported numbers, calibration set | `docs/08-evals.md`, `SETUP.md` §6 |
| Model install, machine prerequisites, audio device setup | `SETUP.md` §4 |
| Waveform UI, mic affordances, degrade banners | `docs/09-ui-ux.md` |

Status vocabulary used throughout: **[decided]**, **[proposed]**, **[open]**. Everything marked
`[proposed]` has a named measurement that settles it (principle 6).

---

## 1. The contract this pipeline must satisfy

Four constraints, in priority order. They conflict; the order is how the conflicts resolve.

| # | Constraint | Why it wins where it wins |
|---|---|---|
| 1 | **The heard source is the scored source.** Whatever audio actually reached the trainee's ear — no more, no less — is what the scoring plane compares the rendering against | Principle 2. Ground truth by construction is worthless if we score against text the trainee never heard. This is why barge-in truncation is a *source-boundary* problem, not a playback problem |
| 2 | **The trainee can always interrupt.** Speech onset during playback stops the AI voice within `barge_in_stop_ms` | Interpreters interrupt. A system that talks over them teaches the wrong reflex |
| 3 | **Conversational gap stays under ~1.2 s.** From the trainee's last speech sample to the counterpart's first audible frame | Above ~2 s the encounter stops feeling like an encounter and the trainee's register drifts to "dictating to a machine" |
| 4 | **The grader never costs the trainee a millisecond.** It runs while the human is talking, or it is shed | Principle 5. This is the load-bearing feasibility claim of the whole architecture |

Constraint 1 outranks constraint 3: if honouring the truncation boundary costs 40 ms, we spend
the 40 ms.

---

## 2. The full audio path, stage by stage

Two directions, both live at once. Naming below matches `src/rehearsal/runtime/audio_in.py`
and `src/rehearsal/runtime/tts.py`.

### 2.1 Inbound — microphone to model

```
  microphone
      │  (analogue)
      ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │ S1  CoreAudio input unit / sounddevice callback                      │
  │     48 kHz float32 mono, 256-frame buffer (~5.3 ms)                  │
  │     REAL-TIME THREAD. No allocation, no locks, no logging.           │
  └───────────────────────────┬──────────────────────────────────────────┘
                              │ lock-free SPSC ring (AudioRing, 30 s capacity)
                              ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │ S2  Resample + frame  →  16 kHz int16, 20 ms frames (320 samples)    │
  │     polyphase 48k→16k, fixed FIR, deterministic                      │
  └───────────────────────────┬──────────────────────────────────────────┘
                              ├──────────────► S3a EchoGuard (§7)
                              ├──────────────► S3b Vad (§5) → Endpointer, BargeInDetector
                              ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │ S4  Utterance assembly                                               │
  │     pre-roll 300 ms retained BEFORE onset (so the first phoneme      │
  │     survives), post-roll trimmed at endpoint minus hangover          │
  └───────────────────────────┬──────────────────────────────────────────┘
                              ├─────► BlobStore: 16 kHz FLAC, content-addressed
                              ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │ S5  ModelHostClient.speak_turn()  →  rehearsal-live (UNIX socket)    │
  │     audio bytes go DIRECTLY into the model. No ASR stage. (§4)       │
  │     returns: {reply_text, heard_verbatim, ...} in one forward pass   │
  └───────────────────────────┬──────────────────────────────────────────┘
                              ▼
                     orchestrator: append `rendering.emitted`,
                     enqueue ScoreRequest (fire-and-forget, §8)
```

### 2.2 Outbound — model to speaker

```
  rehearsal-live token stream (SSE-style frames over the UNIX socket)
      │
      ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │ S6  SourceChunker — accumulate tokens, emit speakable chunks (§6.1)  │
  │     first chunk released at the first terminal punctuation, or at    │
  │     120 chars, whichever comes first                                 │
  └───────────────────────────┬──────────────────────────────────────────┘
                              ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │ S7  TTSRouter.synth(chunk, voice)  — en-US or es-MX                  │
  │     neural backend streams PCM; system `say` backend does not (§6.3) │
  └───────────────────────────┬──────────────────────────────────────────┘
                              ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │ S8  PlaybackQueue — 24 kHz float32, resampled to device rate         │
  │     tracks spoken_ms and spoken_prefix_chars continuously (§6.4)     │
  └───────────────────────────┬──────────────────────────────────────────┘
                              ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │ S9  CoreAudio output unit, 256-frame buffer                          │
  │     cancellation: 20 ms cosine ramp to silence, then flush           │
  └───────────────────────────┬──────────────────────────────────────────┘
                              ▼
                          headphones  (required — §7)
```

### 2.3 Module map

Additions to the tree in `docs/03-system-architecture.md` §4 are marked **new**; everything else
already exists there.

```
src/rehearsal/runtime/
├── audio_in.py      AudioDevice, AudioRing, Resampler, Vad, Endpointer,
│                    BargeInDetector, EchoGuard, UtteranceAssembler
├── tts.py           TTSRouter, SourceChunker, PlaybackQueue, VoiceSpec
├── timing.py        TurnTimer, StageMark, TimingRecord              ← new
└── hosts.py         ModelHostClient, GpuAdmission lease client      (extended, §8.2)
```

One new file. `timing.py` is separate because it is imported by the orchestrator, the scoring
plane and the eval harness, and a circular import through `audio_in` would be the only reason
to merge it.

---

## 3. Latency budget

### 3.1 Stage budgets

Measured on the reference machine in `SETUP.md` §4 (Apple Silicon, 48 GB). All figures are
**per turn**, monotonic-clock deltas (`Event.mono_ms`), p50 unless the row says p95.
"Unacceptable" is not a warning threshold — it is the level at which `BudgetGuard` appends
`budget.exceeded` and the degradation ladder in §10 can fire.

| # | Stage | Event pair (from → to) | Target | Acceptable | Unacceptable | On-path? |
|---|---|---|---|---|---|---|
| S1 | Input device + driver buffer | device callback jitter | 6 ms | 12 ms | > 25 ms | yes |
| S2 | Resample + frame | internal mark | 1 ms | 3 ms | > 8 ms | yes |
| S3b | VAD decision per 20 ms frame | internal mark | 1.5 ms | 4 ms | > 10 ms (p95) | yes |
| S3b′ | Speech-onset declaration | first voiced sample → `onset` mark | 60 ms | 120 ms | > 200 ms | yes |
| S4 | Endpoint hangover (deliberate dead time) | last voiced sample → `capture.ended` | 700 ms | 900 ms | > 1200 ms | yes |
| S4b | Utterance assembly + FLAC encode | `capture.ended` → host request sent | 25 ms | 60 ms | > 150 ms | yes |
| S5a | Audio encode + prefill in `rehearsal-live` | request sent → first token | 220 ms | 400 ms | > 700 ms | yes |
| S5b | Decode to first speakable chunk | first token → chunk released | 130 ms | 260 ms | > 500 ms | yes |
| S5c | Decode to full reply (`source_generation_ms`) | request sent → last token | 900 ms | 1400 ms | > 2200 ms | partly¹ |
| S7 | TTS first PCM (`tts_first_audio_ms`) | chunk released → first PCM frame | 220 ms | 400 ms | > 700 ms | yes |
| S8/S9 | Playback queue + output device | first PCM frame → audible | 20 ms | 40 ms | > 80 ms | yes |
| — | **Barge-in stop** (`barge_in_stop_ms`) | trainee onset → last audible sample | 80 ms | 120 ms | > 250 ms | yes |
| — | Generation cancel ack | cancel sent → host confirms | 40 ms | 100 ms | > 300 ms | no² |
| — | Turn persist (`persist_turn_ms`) | `capture.ended` → event appended | 15 ms | 50 ms | > 200 ms | yes³ |
| G1 | Extractors (all seven) | `score.enqueued` → `extractors.completed` | 30 ms | 80 ms | > 250 ms | **no** |
| G2 | Grader call (`grader_wall_ms`) | `grader.started` → `grader.completed` | 2200 ms | 3500 ms | > 5000 ms | **no** |
| G3 | Verdict merge | `grader.completed` → `verdict.merged` | 2 ms | 10 ms | > 50 ms | **no** |

¹ Only the *first chunk* is on the critical path. Tokens after the first chunk are consumed by
TTS while earlier audio is already playing; S5c only becomes on-path if decode is slower than
speech, which is the `tts_underrun` condition in §6.5.
² The cancel ack is off-path because playback is already silent by then (§9.2). It is budgeted
because a host that will not cancel is a host that will still be generating when the next turn
starts.
³ On-path because the append happens before the next `turn.opened`. It is small and it stays
small; it is listed so that a disk stall is attributed correctly instead of being blamed on the
model.

The default values in `TurnBudget` (`docs/03-system-architecture.md` §6.4) are the
**Acceptable** column, not the Target column. Budgets exist to catch failure, not to describe
success.

### 3.2 The number that actually matters: conversational gap

`T_gap` = trainee's last voiced sample → counterpart's first audible sample. This is the only
latency a human perceives directly, and it is the sum of S4 + S4b + S5a + S5b + S7 + S8/S9.

| | Target | Acceptable | Unacceptable |
|---|---|---|---|
| **T_gap** (p50) | **≤ 1150 ms** | ≤ 1700 ms | > 2500 ms |
| **T_gap** (p95) | ≤ 1500 ms | ≤ 2200 ms | > 3200 ms |

Arithmetic at target: 700 + 25 + 220 + 130 + 220 + 20 = **1315 ms**, which is over the 1150 ms
target. That gap is closed by the one structural saving available, and it is worth naming
plainly rather than hiding in a sum: **speculative TTS start** (§6.2) overlaps S7 with the tail
of S5b, and the adaptive endpointer (§5.3) drops S4 to 500 ms on utterances that end in a
confident falling contour with a long preceding speech run. Realistic target path:
500 + 25 + 220 + 130 + (220 overlapped → ~90 marginal) + 20 = **985 ms**.

**Honest note [decided].** Natural human conversational gaps run roughly 200 ms. We are not
going to reach that, and we do not claim we will. Consecutive interpreting has genuinely longer
gaps than free conversation — the interpreter pauses, the clinician waits — so ~1 s reads as
"a person thinking", not as "a machine lagging". Above ~2.5 s it reads as lag. That is the
honest framing and it is what `docs/08-evals.md` reports: a distribution with n and p95, never
a single reassuring average.

### 3.3 What is deliberately *not* in the budget

| Excluded | Why |
|---|---|
| ASR / speech recognition | There is no such stage. See §4 |
| Network round trips | No cloud inference in the core loop. There is no network in the critical path at all |
| Grader, coach, learner update | Off-path by construction (§8). If any of them ever appears in `T_gap`, that is a scheduling bug with a test (§8.4) |
| Frontend render | The SPA is a projection of the event log over a local WebSocket; a slow browser degrades the display, never the audio path (`docs/09-ui-ux.md`) |

---

## 4. Why native audio input removes a stage

The conventional pipeline is: mic → ASR → text → LLM → text → TTS → speaker. Rehearsal's is:
mic → LLM (audio in) → text → TTS → speaker.

| | Conventional | Rehearsal |
|---|---|---|
| Serial stages before first token | ASR decode (250–600 ms for a 6 s utterance, even streaming) **then** LLM prefill | LLM prefill over audio tokens only |
| Error surfaces between trainee and agent | two (ASR errors, then model errors) | one |
| Resident memory | ASR model + LLM | LLM |
| Failure modes | ASR device/model failure is its own outage class | fewer moving parts |

The saving is not merely "one fewer model". It is one fewer **serial** stage on the tightest
budget in the system, and — more importantly for this product — one fewer place where Spanish,
code-switching, Mixteco-influenced Spanish phonology, and clinic-register speech can be silently
mangled before the agent ever sees it. An ASR system trained on broadcast Spanish mis-hearing a
Pajaro Valley speaker would corrupt the encounter itself, not just the transcript.

**The obligation this creates.** The scoring plane needs *text* for the rendering. The live
agent's structured output carries `heard_verbatim` alongside its in-character reply, produced
in the same forward pass, so it costs no extra critical-path latency
(`docs/03-system-architecture.md` §7). That is only sound if `heard_verbatim` is faithful. It is
therefore measured against hand transcripts of the calibration audio, reported in
`docs/08-evals.md`, and if it fails the bar the fallback is an off-path re-transcription pass on
the grader host (`rendering_source = "offpath_retranscribe"`) — which spends latency the scoring
plane has and the runtime does not. This is the single largest open technical risk in the voice
pipeline and it is tracked as such (§13).

**What we give up [decided].** No partial transcript during speech. A streaming ASR would let
the UI show words as they are spoken; native audio input gives us nothing until the utterance
closes. The UI shows a level meter and elapsed time instead (`docs/09-ui-ux.md`). We judged live
captions to be a comfort feature and the removed stage to be a structural win; if trainer
feedback says captions are pedagogically necessary, they come back as an *off-path* pass that
populates the replay view, never as a critical-path stage.

---

## 5. Turn-taking and endpointing

### 5.1 Voice activity detection

```python
# src/rehearsal/runtime/audio_in.py

class Vad(Protocol):
    """Frame-synchronous voice activity detection. 20 ms int16 mono @ 16 kHz."""
    def push(self, frame: bytes) -> float: ...   # returns P(speech) in [0, 1]
    def reset(self) -> None: ...
```

| Backend | Model | When used | Cost |
|---|---|---|---|
| `SileroVad` **[decided, dependency approval pending]** | Silero VAD v5, ONNX, ~2 MB, `onnxruntime` CPU | default | ~0.9 ms per 20 ms frame, one core |
| `RmsVad` | RMS + zero-crossing over a rolling noise floor, stdlib + `numpy` | fallback if `onnxruntime` is unavailable; also the L3+ degrade path | ~0.05 ms per frame |

`RmsVad` is not a toy — it is calibrated against the room's noise floor during the 2 s
`rehearsal doctor --audio` room-tone measurement — but it is materially worse at rejecting
keyboard clicks and clinic-like background chatter, and that is exactly the difference between
a false endpoint and a clean one. The dependency buys measurable behaviour, which is the only
reason to add one. **[open]** — the A/B (false-endpoint rate, both backends, same 30 recorded
utterances) is specified in `docs/08-evals.md`.

### 5.2 The endpointer state machine

```python
@dataclass(frozen=True, slots=True)
class EndpointPolicy:
    speech_threshold:      float = 0.55   # P(speech) to count a frame voiced
    silence_threshold:     float = 0.35   # hysteresis: below this counts unvoiced
    onset_frames:          int   = 3      # 60 ms continuous voiced → onset declared
    hangover_ms:           int   = 700    # base end-of-speech silence
    hangover_short_ms:     int   = 1100   # if utterance so far < 1200 ms (likely false start)
    hangover_long_ms:      int   = 500    # if utterance > 4000 ms and trailing energy falling
    resume_grace_ms:       int   = 600    # false-endpoint retraction window (§5.4)
    preroll_ms:            int   = 300    # audio retained before onset
    min_utterance_ms:      int   = 250    # shorter than this is a cough, not a turn
    capture_max_ms:        int   = 45_000 # hard cap; matches TurnBudget
```

States, all deterministic, no model involved:

```
       ┌───────────┐  3 voiced frames        ┌──────────┐
  ─────► listening ├────────────────────────► speaking │
       └─────▲─────┘                         └────┬─────┘
             │                                    │ unvoiced run begins
             │ retract (§5.4)              ┌──────▼──────┐
             │                             │  hangover   │◄── voiced frame: back to speaking
       ┌─────┴─────┐  no resume within     └──────┬──────┘
       │  closed   │◄──────────────────────────── │ hangover elapsed
       └───────────┘  resume_grace_ms              → emit capture.ended
```

Hysteresis (0.55 up / 0.35 down) exists because a single-threshold VAD chatters on breath and
fricatives, and every chatter is a candidate false endpoint.

### 5.3 Adaptive hangover

One rule, three branches, all decidable from signals we already have:

| Condition on the utterance so far | Hangover | Rationale |
|---|---|---|
| duration < 1200 ms | 1100 ms | Short utterances are usually false starts ("Ella dice — el paciente dice…"). Waiting costs a beat; cutting costs the whole rendering |
| duration > 4000 ms **and** trailing 400 ms RMS below 60 % of the utterance mean | 500 ms | Long run plus falling energy is a completed clause. Trim aggressively; this is where the T_gap target is actually met |
| otherwise | 700 ms | Default |

**Explicitly rejected [decided]:** a model-based "is this utterance semantically complete"
endpointer. It puts a language model on the tightest budget in the system to decide something
we can approximate deterministically, and principle 1 says decidable things are decided by code.
The cost of being occasionally wrong is one retraction (§5.4), which is cheap and visible.

### 5.4 False-endpoint recovery

The endpointer *will* fire early — the trainee pauses to retrieve a term, and clinical
interpreting is full of exactly that pause. The recovery rule:

| Situation when the trainee resumes | Action | Event |
|---|---|---|
| Within `resume_grace_ms` (600 ms) of `capture.ended`, **and** no counterpart audio is yet audible | **Retract.** Splice the new speech onto the buffered utterance, discard the pending host request (cancel in flight), return to `speaking` | `capture.reopened` **(new event kind — §13)** |
| After counterpart audio has become audible | Not a retraction. This is barge-in on the *next* turn (§9); the previous rendering stands as captured | `tts.interrupted` |
| Within grace but the host request already returned | Retract anyway; the returned reply is discarded and regenerated from the spliced audio, with the same derived seed | `capture.reopened`, plus `source.requested` reissued |

The 600 ms grace is chosen so that a retraction is always cheaper than the alternative: at
target timings, nothing is audible until ~615 ms after `capture.ended`, so the grace window
closes almost exactly when the window of harmless retraction closes. If measured S5a+S5b+S7
drops on faster hardware, `resume_grace_ms` must drop with it — `rehearsal doctor` writes the
machine-local value into `budget.local.json` and this is one of the values it writes.

Retracted turns are **counted and reported**: `turn_timings.retractions` (§11). A rising
retraction rate is the signal that `hangover_ms` is too low for this trainee or this room, and
it is surfaced in the trainer view rather than silently auto-tuned. Auto-tuning a threshold that
changes what gets scored would make two sessions incomparable without either of them saying so.

### 5.5 Empty and over-long renderings

| Case | Rule |
|---|---|
| Silence exceeding `capture_max_ms` with no onset | `rendering.emitted` with `empty: true`; the turn is scored as a full omission (`docs/06-scoring-engine.md`) |
| Onset present but total voiced < `min_utterance_ms` | Not an utterance. Discarded, endpointer returns to `listening`, no event |
| Utterance reaches `capture_max_ms` while still speaking | Hard close at the cap; `capture.ended` carries `truncated: true`. The turn is scored, and the truncation flag is carried into the verdict so a spurious omission can be attributed |

---

## 6. Output: streaming, chunking, speculative TTS

### 6.1 Chunking

```python
# src/rehearsal/runtime/tts.py

class SourceChunker:
    """Token stream → speakable chunks. Deterministic; no model involved."""
    def push(self, token_text: str) -> list[Chunk]: ...
    def flush(self) -> list[Chunk]: ...
```

Emission rule, in order:

1. Terminal punctuation (`. ! ? ¡ ¿ … : ;`) followed by whitespace → emit.
2. No terminal punctuation for 120 characters → emit at the last clause boundary (`, ' y ' ' o '
   ' pero ' ' que ' / `, ' and ' ' but ' ' so '`), else at the last word boundary.
3. Never emit a chunk shorter than 12 characters unless it is the flush.
4. Spanish inverted openers (`¿`, `¡`) never terminate a chunk — they open one. This is the kind
   of detail that produces audibly wrong prosody in a bilingual system if nobody writes it down.

Chunk boundaries are recorded with their character offsets into the reply text. This is not
cosmetic: it is what makes the truncation boundary in §6.4 exact.

### 6.2 Speculative TTS start

TTS synthesis for chunk *k* begins the moment chunk *k* is emitted, while the model is still
decoding chunk *k+1*. For the first chunk this overlaps S7 with the tail of S5b and is worth
roughly 130 ms of `T_gap`.

**Why this is safe and not actually speculative in the risky sense:** decoding is left-to-right
and the model does not revise emitted tokens. A chunk, once emitted, is final. The only thing
"speculative" about it is prosodic — the synthesiser cannot see the following clause, so
sentence-final intonation may be applied to what turns out to be a continuation. Mitigations:

| Risk | Mitigation |
|---|---|
| Wrong sentence-final contour | Rule 2 emits at *clause* boundaries and the neural backend is given a `continues: true` flag on non-terminal chunks |
| Audible seam between chunks | 15 ms equal-power crossfade at chunk joins in `PlaybackQueue` |
| Decode slower than speech (underrun) | §6.5 |

**Rejected [decided]:** synthesising a generic filler ("mmm", "let me see") to mask latency.
It teaches the trainee to interpret a disfluency that the system inserted, and disfluency
handling is a real interpreting competency we must not fake.

### 6.3 Backends

```python
class VoiceSpec(NamedTuple):
    lang: Literal["en-US", "es-MX"]
    voice_id: str
    rate: float          # 0.8–1.25, the difficulty knob (docs/07-data-and-scenarios.md)
    sample_rate: int     # native rate of the backend

class TTSBackend(Protocol):
    streaming: bool
    def synth(self, chunk: Chunk, voice: VoiceSpec) -> Iterator[bytes]: ...  # PCM float32
    def cancel(self, chunk_id: str) -> None: ...
```

| Backend | Streaming | First-PCM p50 | Memory | Role |
|---|---|---|---|---|
| `NeuralTTS` (local, two voices) | yes, ~80 ms granularity | 220 ms | ~1.5 GB | default |
| `SystemVoiceTTS` (macOS `say` → AIFF → PCM) | **no** — utterance-granular | 380 ms | ~0 (OS) | DegradeLevel L3 |

`SystemVoiceTTS` not being streaming is the reason L3 is a *degradation* and not an equivalent
alternative: cancellation granularity drops to the chunk, so barge-in stop time rises to roughly
one chunk of audio in the worst case. `PlaybackQueue` compensates by capping chunk length at
2.5 s of estimated audio when the non-streaming backend is active, bounding worst-case barge-in
stop at 2.5 s of *queued* audio — but the ramp-to-silence still happens within 120 ms because
cancellation is enforced at the *playback* layer, not the synthesis layer. This is the whole
reason cancellation lives in `PlaybackQueue`.

### 6.4 The spoken prefix — where playback meets ground truth

`PlaybackQueue` maintains, continuously and monotonically:

```python
@dataclass(slots=True)
class PlaybackCursor:
    spoken_ms: int              # audio actually delivered to the output device
    spoken_prefix_chars: int    # chars of reply_text fully covered by delivered audio
    last_chunk_id: str
    complete: bool
```

`spoken_prefix_chars` advances only at chunk boundaries — we know a chunk's character span
exactly, and we know when its last PCM frame left the queue. Within a chunk we do **not**
interpolate to a character offset, because a linear time-to-character mapping inside synthesised
speech is a guess, and a guess here would silently change what the trainee is scored against.

On interruption, the source of record for scoring is `reply_text[:spoken_prefix_chars]`, plus
the partially-spoken chunk **flagged, not included**:

```json
{
  "kind": "tts.interrupted",
  "d": {
    "spoken_ms": 3120,
    "spoken_prefix_chars": 148,
    "partial_chunk_id": "c7",
    "partial_chunk_text": "y necesito saber si le duele al respirar",
    "partial_chunk_spoken_ms": 410,
    "partial_chunk_est_total_ms": 1900
  }
}
```

The scoring plane's rule for the partial chunk is **[proposed]**, matching open item 2 in
`docs/03-system-architecture.md` §16: the partial chunk is excluded from the scored source, and
the turn carries `source_truncated: true`. If trainer review shows that excluding it produces
spurious *additions* (the trainee rendered material we decided they never heard), the rule flips
to "include, and mark the turn unscoreable for omission". This is settled by trainer judgement
on recorded cases, not by argument.

### 6.5 Underrun

If `PlaybackQueue` empties while the reply is incomplete — decode slower than speech — the
counterpart appears to stop mid-sentence, which the trainee will read as a turn boundary and
start interpreting.

| Trigger | Action |
|---|---|
| Queue depth < 250 ms of audio with tokens still pending | Append `budget.exceeded` stage `tts_underrun`; do **not** insert filler |
| Two underruns in one turn, or three in a session | Degrade: cap `max_new_tokens` for source generation (L1u, §10) |
| Underrun occurs | The gap is real audio silence; if the trainee starts speaking into it, it is treated as barge-in and the spoken-prefix rule applies exactly as in §6.4 |

We never paper over an underrun. A trainee interpreting a truncated source is a legitimate,
scoreable event as long as the boundary is recorded honestly; a system that hides the truncation
produces a verdict nobody can defend.

---

## 7. Echo, feedback, and the headphone requirement

**Headphones are a hard requirement for a scored session. [decided]**

Without them, the counterpart's TTS output re-enters the microphone. Three failures follow, in
increasing order of badness:

1. The barge-in detector triggers on the AI's own voice and cuts it off mid-utterance.
2. The endpointer never closes, because the room never goes quiet.
3. **The model hears its own voice as the trainee's rendering and scores it.** A verdict computed
   over the TTS voice is not a wrong number, it is a fabricated one.

Failure 3 is the reason this is a requirement and not a recommendation.

### 7.1 EchoGuard

```python
class EchoGuard:
    """Rejects inbound frames that correlate with recently played output."""
    def note_output(self, frame: bytes, mono_ms: int) -> None: ...
    def is_echo(self, frame: bytes, mono_ms: int) -> bool: ...
    def coupling_estimate(self) -> float:   # 0.0 isolated … 1.0 fully open-air
```

Mechanism: normalised cross-correlation between the inbound 20 ms frame and the output frames
delivered over the preceding 20–180 ms window (covering plausible room delay), computed on 16 kHz
band-limited envelopes rather than raw samples — cheap (~0.3 ms/frame) and robust to speaker
colouration. Correlation above 0.62 with a consistent lag marks the frame as echo. It is
*rejection*, not cancellation: we are not building an AEC.

### 7.2 Enforcement ladder

| Check | When | Behaviour |
|---|---|---|
| Output device is not the built-in speaker | Session arm | Pass silently |
| Output **is** built-in speaker | Session arm | Blocking modal: headphones required. The trainee may continue in **practice mode**, which runs the full loop but marks the session `unscored_echo_risk` and excludes it from every reported number |
| `coupling_estimate() > 0.35` sustained for 2 s during playback | Live | `degraded.entered` trigger `echo_coupling`; hard-warn banner (`docs/09-ui-ux.md`); scoring for affected turns is marked `partial` |
| `coupling_estimate() > 0.7` | Live | Session pauses. Continuing would produce fabricated verdicts |

`rehearsal doctor --audio` runs a 2 s calibration tone and reports the measured coupling before
a session ever starts, so this is normally caught at setup rather than mid-encounter.

**Rejected [decided]:** acoustic echo cancellation. A real AEC is a hard DSP problem with a long
tail of failure modes, it would sit on the real-time thread, and it would convert an *obvious*
failure (screeching feedback, an unmistakable "put your headphones on") into a *subtle* one
(mostly-cancelled echo occasionally scored as speech). Detect-and-refuse is both less code and
more honest. `# ponytail: detection not cancellation — headphones are the fix`

---

## 8. Scheduling: keeping the grader off the critical path

Principle 5 is a scheduling claim, and scheduling claims are where architectures quietly fail.
Three resources are contended: CPU cores, the single GPU, and memory bandwidth. The grader must
lose all three contests, every time.

### 8.1 Thread and process model

| Worker | Where | Priority / QoS | Rule |
|---|---|---|---|
| CoreAudio input callback | `rehearsal-api`, RT thread | CoreAudio real-time | No allocation, no locks, no logging, no Python object creation in the hot path. Writes to `AudioRing` only |
| CoreAudio output callback | `rehearsal-api`, RT thread | CoreAudio real-time | Reads `PlaybackQueue`; the *only* place the ramp-to-silence is applied |
| VAD / EchoGuard | `rehearsal-api`, dedicated thread | `USER_INTERACTIVE` | Drains `AudioRing`, runs S2/S3. Never blocks on I/O |
| Orchestrator | `rehearsal-api`, asyncio loop | `USER_INITIATED` | State machine, event appends, host calls |
| Scoring plane | `rehearsal-api`, `ScoreQueue` worker | `UTILITY` | Extractors (CPU) + grader host calls |
| `rehearsal-live` | separate process | `USER_INITIATED`, `nice 0` | Holds the GPU during live decode |
| `rehearsal-grader` | separate process | `BACKGROUND`, `nice 10`, launched under `taskpolicy -b` | Yields the GPU on demand (§8.2) |

Python's GIL is not a factor for the RT threads (they are in the audio library's C callback) nor
for model inference (in the host processes). It *is* a factor between the VAD thread and the
asyncio loop; the VAD thread's per-frame work is ~1.2 ms of mostly-numpy/ONNX work that releases
the GIL, and the measured p95 frame-service jitter is one of the numbers `rehearsal doctor`
reports.

### 8.2 GPU admission control

This is the mechanism that makes principle 5 true rather than merely intended. The GPU cannot
be preempted mid-kernel, so "the live model has priority" has to be implemented as *the grader
never holds a long command buffer*.

```python
# src/rehearsal/runtime/hosts.py

class GpuAdmission:
    """Single-writer lease over GPU-heavy work. Held by rehearsal-api."""
    def acquire_live(self) -> LeaseToken: ...          # never waits; preempts pending grader admission
    def try_acquire_grader(self, max_submission_ms: int) -> LeaseToken | None: ...
    def release(self, token: LeaseToken) -> None: ...
    def live_active(self) -> bool: ...
```

Rules, all deterministic:

1. `rehearsal-grader` must hold a lease to submit work. It requests one per **decode window**,
   not per request.
2. A grader lease is granted only when `live_active()` is false, and it is granted with
   `max_submission_ms = 25`. The grader host caps its per-submission token batch so that a single
   Metal command buffer stays under that. Worst-case blocking of a live request is therefore one
   in-flight grader submission (~25 ms), not one grader *request* (~2200 ms).
3. When the orchestrator is about to call `rehearsal-live`, it calls `acquire_live()` *before*
   sending the request. Pending grader leases are refused from that moment; in-flight ones drain.
4. Prefill for the live model is issued as one submission and is never interleaved.

The 25 ms cap is a knob, not a law: it trades grader throughput for live tail latency, and
`rehearsal doctor` measures both and can lower it on slower hardware.

### 8.3 The overlap

The full picture is in `docs/03-system-architecture.md` §6.2. The voice-pipeline-relevant
restatement: **scoring for turn *N* is launched at `rendering.emitted` for turn *N*, which is
before `tts.started` for turn *N+1*.** The grader therefore runs during the counterpart's next
utterance *and* during the trainee's next rendering — a window of roughly 4–12 s against a
budget of 3.5 s.

The window is not guaranteed. A trainee who renders a five-word turn in 2 s gives the grader
less window than the grader needs; that is what `should_shed()` and DegradeLevel L1/L2 are for
(`docs/03-system-architecture.md` §14). The verdict lands late, the coach hint is dropped, the
loop does not block.

### 8.4 The test that keeps this honest

An assertion, not a hope. In `evals/` (harness detail in `docs/08-evals.md`):

> Across a recorded session replayed with the grader forced to its p99 latency, the p95 of
> `T_gap` must not differ from the same session replayed with the grader disabled by more than
> **40 ms**.

If the grader is stealing latency, this number moves. It is reported per release. Any change to
`GpuAdmission`, the QoS table, or the host process model re-runs it.

---

## 9. Barge-in

### 9.1 Detection

Barge-in detection is deliberately *stricter* than ordinary onset detection, because a false
positive cuts off the counterpart mid-sentence and destroys the encounter's realism.

| Parameter | Listening (no playback) | During playback (barge-in) |
|---|---|---|
| Voiced frames required | 3 (60 ms) | 12 (240 ms) |
| `speech_threshold` | 0.55 | 0.70 |
| EchoGuard | advisory | **mandatory** — any frame flagged as echo does not count |
| Minimum inbound level | noise floor + 6 dB | noise floor + 10 dB |

240 ms costs a fifth of a second of the counterpart still talking over the trainee. That is the
right trade: a spurious cut is far more disruptive than a slightly late one, and interpreters
routinely begin rendering the moment a clause closes, which is exactly when a laxer detector
would fire on a breath.

Barge-in can be disabled per scenario (`allow_barge_in: false` in the scenario definition,
`docs/07-data-and-scenarios.md`) for drills that specifically train waiting for the full
utterance.

### 9.2 The cancellation sequence

Order matters, and it is fixed. Steps 1–2 are what the human perceives; the rest can take their
time.

```
t+0     BargeInDetector fires
t+0     PlaybackQueue.cancel()      → output callback applies a 20 ms cosine ramp,
                                      then flushes every queued chunk
t+20ms  audio is silent                        ◄── barge_in_stop_ms clock stops here
t+20ms  PlaybackCursor frozen; spoken_ms and spoken_prefix_chars read once and held
t+22ms  TTSRouter.cancel(chunk_id) for every in-flight and queued chunk
t+25ms  ModelHostClient.cancel(req_id) → rehearsal-live stops decoding
t+25ms  append `tts.interrupted` with the frozen cursor (§6.4)
t+26ms  UtteranceAssembler starts the trainee's capture, INCLUDING the 300 ms pre-roll
        (the trainee's first phoneme happened before detection fired — it must not be lost)
t+~70ms host acknowledges cancel; partial reply_text retained in the turn record
t+~70ms state → rendering_capturing
```

**Silence first, bookkeeping second.** Cancelling generation before silencing playback would be
correct-looking and wrong: the queue still holds 200–800 ms of already-synthesised audio and the
trainee would keep hearing the counterpart after "cancellation".

The 300 ms pre-roll at step t+26ms is not optional. Detection requires 240 ms of voiced audio,
so by the time we know the trainee is speaking, they have already said a syllable or two. Those
samples are in `AudioRing` and they belong to the rendering.

### 9.3 Turn-state consistency

The invariant: **after any barge-in, exactly one turn is open, its source is the spoken prefix,
and every event is appended in causal order.**

| Hazard | Guard |
|---|---|
| Host returns the full reply after cancel was sent | Reply is discarded; `spoken_prefix_chars` already froze the source. The late response is logged, not used |
| Cancel is not acknowledged within 300 ms | `host.restarted` path; playback is already silent so the trainee is unaffected. The turn is marked `source_truncated` and `host_cancel_timeout` |
| Barge-in fires during the *first* chunk, before any audio played | `spoken_prefix_chars == 0`. The turn is abandoned entirely (`turn.abandoned`), not scored, and the graph does not advance. Scoring a rendering of nothing would manufacture an omission |
| Barge-in and false-endpoint retraction race | Retraction (§5.4) is only possible before audio is audible; barge-in is only possible after. They are mutually exclusive by construction, and there is a unit test that asserts it |
| Trainee barges in, then falls silent immediately (cough) | Utterance shorter than `min_utterance_ms` → the turn is *resumed*: `tts.resumed` is **not** implemented (see §13); instead the turn is closed with the truncated source and the graph advances. **[proposed]** |

That last row is the one soft edge in this section and it is flagged rather than smoothed. The
alternative — resuming playback from `spoken_ms` — requires re-synthesising from a mid-chunk
offset, which reintroduces exactly the time-to-character interpolation §6.4 refuses to do.

---

## 10. Memory layout and the degradation ladder

### 10.1 Resident memory on a 48 GB machine

Unified memory: model weights, KV cache and OS all draw from the same pool, so "GPU memory" and
"RAM" are the same budget. Figures are steady-state resident during a live session with a
40-turn scenario.

| Component | Process | Weights | KV cache | Activations / buffers | Total |
|---|---|---|---|---|---|
| Gemma 4 E4B, 4-bit, audio-native | `rehearsal-live` | 4.6 GB | 1.4 GB¹ | 0.6 GB | **6.6 GB** |
| Gemma 12B, 4-bit | `rehearsal-grader` | 7.1 GB | 1.6 GB² | 0.7 GB | **9.4 GB** |
| Neural TTS, two voices | `rehearsal-tts` or in-process | 1.4 GB | — | 0.15 GB | **1.55 GB** |
| Orchestrator, FastAPI, SQLite, event log | `rehearsal-api` | — | — | 0.35 GB | **0.35 GB** |
| Audio: `AudioRing` (30 s @ 48 kHz f32 stereo ≈ 11 MB), `PlaybackQueue`, FLAC staging | `rehearsal-api` | — | — | 0.10 GB | **0.10 GB** |
| ONNX VAD + runtime | `rehearsal-api` | 2 MB | — | 0.05 GB | **0.05 GB** |
| | | | | **Rehearsal total** | **≈ 18.1 GB** |
| macOS + WindowServer + Metal driver | — | | | | ≈ 4.5 GB |
| Browser running the SPA | — | | | | ≈ 1.5 GB |
| | | | | **System total** | **≈ 24.1 GB** |
| | | | | **Free headroom** | **≈ 24 GB** |

¹ Live agent context is capped at 4096 tokens per agent by the `ContextAssembler` allowlist
(`docs/03-system-architecture.md` §12); two agents share the host with separate caches.
² Grader context is a single structured call, capped at 8192 tokens.

This sits at the low end of the ~20–24 GB target in `SETUP.md` §4 because the table above is
steady state; transient peaks during model load and during the first prefill of a long grader
context are what consume the remainder. The headroom is not slack to be spent — it absorbs
memory-pressure spikes without the kernel compressing or swapping model pages, and a swapped
model page is a 400 ms stall in a 220 ms budget.

**Load order [decided]:** `rehearsal-live` first, then TTS, then `rehearsal-grader` last. The
grader is the one component that may be killed and restarted freely (`docs/03-system-architecture.md`
§5), so it gets the memory that is left rather than the memory it prefers. If `rehearsal-grader`
cannot be allocated at all, the session starts at DegradeLevel L2 and says so — it does not
refuse to start.

**Explicitly not done:** raising `iogpu.wired_limit_mb`. That is a system-level setting; changing
it is the user's decision and it is documented in `SETUP.md` §4, not performed by the product.

### 10.2 Voice-specific degradation triggers

The ladder itself is defined in `docs/03-system-architecture.md` §14 and is not restated. What
follows is the voice pipeline's contribution: the **measurable trigger** for each rung, and the
voice-only sub-levels that sit under L1 and L2.

| Rung | Measurable trigger (all on monotonic-clock data from §11) | Voice-side action | Reversible? |
|---|---|---|---|
| **L0** nominal | — | Full loop | — |
| **L1u** shorter source | Two `tts_underrun` events in one turn, or three in a session | `max_new_tokens` for source generation drops 512 → 320; the state graph is told to prefer shorter node realisations | Yes — restored after 5 clean turns |
| **L1** hint shed | `ScoreQueue` depth ≥ 2 | Coach TTS suppressed entirely (the coach voice competes for the same TTS backend) | Yes |
| **L2s** speculative off | Chunk-seam artefacts reported, or crossfade CPU starving the VAD thread (VAD p95 frame service > 10 ms) | Speculative start disabled; TTS waits for the full reply. Costs ~130 ms of `T_gap` and says so in the debrief | Yes |
| **L2** grader shed | Grader p95 > `grader_wall_ms` over 3 consecutive turns, or `rehearsal-grader` unreachable | Grader host suspended; extractor-only verdicts marked `partial`. Frees ~9.4 GB and all GPU contention | Yes, on 5 consecutive turns under budget |
| **L2m** smaller live model | `T_gap` p95 > 2500 ms over 5 consecutive turns **and** the grader is already shed | `rehearsal-live` restarts on the smaller quantisation of the same checkpoint (see `SETUP.md` §4). This changes agent behaviour, so the session is marked `model_switched` and its persona-consistency numbers are reported separately | **No** — not within a session |
| **L3** TTS fallback | Neural TTS first-PCM p95 > 700 ms over 3 turns, backend load failure, or two synthesis exceptions | `SystemVoiceTTS`; chunk cap 2.5 s (§6.3) | Yes |
| **L3e** echo | `EchoGuard.coupling_estimate() > 0.35` for 2 s | Hard-warn banner; affected turns marked `partial`; above 0.7 the session pauses (§7.2) | Yes, when coupling drops |
| **L4** text mode | Audio device unavailable > 10 s and the trainee opts to continue | Source shown as text, rendering typed. Session marked `text_mode` and **excluded from every voice-latency statistic** | No |
| **L5** stop | Below `cfg.degrade_floor`, or the store is unwritable | Clean abort with a complete log prefix | — |

Every transition appends `degraded.entered` / `degraded.exited` carrying the numeric trigger
value — not just the rung name. "Entered L2 because grader p95 was 4180 ms over turns 7–9" is a
sentence a trainer can act on; "entered L2" is not.

**The ordering rationale.** We shed *analysis* (L1, L2) before we shed *fidelity of the
encounter* (L2m, L3), and we shed the encounter's polish before we shed the encounter itself
(L4). A trainee can learn from a session with delayed feedback. A trainee cannot learn from a
session where the patient sounded like a 1998 speech synthesiser and the register cues they were
supposed to catch were never in the audio.

---

## 11. Instrumentation

### 11.1 What is captured per turn

Every stage boundary in §3.1 emits a `StageMark` on the monotonic clock. Wall-clock time is
recorded once per turn; all arithmetic uses `mono_ms`, because wall clock is not sound across
sleep/wake (`docs/03-system-architecture.md` §10.3).

```python
# src/rehearsal/runtime/timing.py

STAGES: Final = (
    "capture_onset", "capture_end", "assemble", "host_request", "first_token",
    "first_chunk", "tts_first_pcm", "first_audible", "reply_complete",
    "playback_complete", "persist",
    "score_enqueued", "extractors_done", "grader_start", "grader_done", "verdict_merged",
)

class TurnTimer:
    def mark(self, stage: str) -> None: ...
    def span(self, a: str, b: str) -> int | None: ...
    def record(self) -> TimingRecord: ...
```

### 11.2 The projection

`turn_timings` is a **projection**, rebuildable from the event log by `rehearsal replay`
(`docs/03-system-architecture.md` §10.1). It exists because latency queries against a
hash-chained event log are painful, not because it is a second source of truth.

```sql
CREATE TABLE turn_timings (
  session_id        TEXT    NOT NULL,
  turn_index        INTEGER NOT NULL,

  -- the headline number
  t_gap_ms          INTEGER,          -- capture_end → first_audible

  -- inbound
  onset_detect_ms   INTEGER,          -- first voiced sample → capture_onset
  speech_ms         INTEGER,          -- voiced duration of the rendering
  hangover_used_ms  INTEGER,          -- which branch of §5.3 fired
  assemble_ms       INTEGER,          -- capture_end → host_request

  -- live model
  prefill_ms        INTEGER,          -- host_request → first_token
  to_first_chunk_ms INTEGER,          -- first_token → first_chunk
  decode_total_ms   INTEGER,          -- host_request → reply_complete
  reply_tokens      INTEGER,

  -- outbound
  tts_first_pcm_ms  INTEGER,          -- first_chunk → tts_first_pcm
  output_latency_ms INTEGER,          -- tts_first_pcm → first_audible
  playback_ms       INTEGER,          -- first_audible → playback_complete
  tts_backend       TEXT    NOT NULL, -- 'neural' | 'system'
  underruns         INTEGER NOT NULL DEFAULT 0,

  -- interaction
  barge_in          INTEGER NOT NULL DEFAULT 0,   -- 0/1
  barge_in_stop_ms  INTEGER,                      -- onset → last audible sample
  retractions       INTEGER NOT NULL DEFAULT 0,   -- false endpoints recovered (§5.4)
  source_truncated  INTEGER NOT NULL DEFAULT 0,
  spoken_prefix_chars INTEGER,
  reply_chars       INTEGER,

  -- off-path (recorded here so "did it stay off-path" is one query)
  extractors_ms     INTEGER,
  grader_ms         INTEGER,
  grader_late       INTEGER NOT NULL DEFAULT 0,   -- landed after next capture_end
  score_queue_depth INTEGER,

  -- health context; a latency number without these is uninterpretable
  degrade_level     INTEGER NOT NULL DEFAULT 0,
  vad_backend       TEXT    NOT NULL,             -- 'silero' | 'rms'
  echo_coupling     REAL,
  vad_frame_p95_ms  REAL,
  input_device      TEXT,
  output_device     TEXT,

  PRIMARY KEY (session_id, turn_index)
);

CREATE INDEX idx_tt_gap ON turn_timings(t_gap_ms);
```

`degrade_level`, `tts_backend`, `vad_backend` and `echo_coupling` are on every row for one
reason: a `t_gap_ms` of 900 recorded at L2 with the system voice is not the same measurement as
a 900 recorded at L0, and the schema must make it impossible to pool them by accident.

### 11.3 Reporting

```
rehearsal doctor --audio            # pre-flight: device round-trip, room tone,
                                    #   echo coupling, VAD frame service, one synthetic turn
rehearsal report --timings <sid>    # per-session table + the stage waterfall
rehearsal report --timings --all    # cross-session distributions
rehearsal replay --timings <sid>    # rebuild turn_timings from events (verifies the projection)
```

Reporting rules, from principle 7:

| Rule | Consequence |
|---|---|
| Report **distributions**, never a lone mean | Every latency figure ships as p50 / p95 / max with **n** |
| Never pool across degrade levels | Every table is faceted by `degrade_level`; a footnote states how many turns sat at each |
| `text_mode` sessions are excluded from voice statistics | They contain no voice |
| n < 30 turns is reported as such | Below that the p95 is a rumour, and it is labelled `p95 (n=17, wide)` |
| The first turn of every session is reported separately | It carries model warm-up and is not representative. Excluding it silently would be flattering; excluding it visibly is honest |
| Machine identity accompanies every published number | An 48 GB M-series figure is not a claim about any other machine |

The default operator view is a stage waterfall, ASCII, so it renders in a terminal and pastes
into a log:

```
session 7f3a…  turn 12   T_gap 1042 ms   L0   neural/silero
  hangover      ████████████████████████████               700
  assemble      █                                           24
  prefill       ████████                                   208
  first chunk   █████                                      121
  tts first pcm █                                          (overlapped, +71 marginal)
  output        █                                           18
                                                   T_gap  1042  ✓ target ≤1150
  off-path:  extractors 34   grader 2180   queue depth 0   grader_late 0
```

---

## 12. ASCII timing diagram of one full turn

Turn *N*: the clinician speaks English, the trainee interprets into Spanish, and turn *N*'s
scoring runs underneath it all. Time axis is milliseconds from the start of turn *N*; the figures
are the §3.1 targets, so this is the intended shape, not a measured trace.

```
   0        500       1000      1500      2000      2500      3000      3500      4000      4500 ms
   ├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤

RUNTIME — turn N source (clinician, en-US)
   ├ turn.opened
   ├─ acquire_live()
   │  ┌ host_request
   │  ├──── prefill 220 ──────┐
   │                          ├ first_token
   │                          ├─ decode → first_chunk (130) ─┐
   │                                                         ├ chunk c0 released
   │                                                         ├── TTS synth 220 ──┐
   │                                                                             ├ tts.started
   │                                                                             │ first_audible
   │                                                    ┌── SPEAKING ────────────┴──────────────┐
   │                                                    │ c0 ══ c1 ══ c2 ══ c3   (decode of c1+ │
   │                                                    │ overlaps playback of c0 — §6.2)       │
   │                                                    └──────────────────── tts.finished ─────┤
   │                                                                                            │
RUNTIME — turn N rendering (trainee, es-MX)                                                     │
   │                                                                       capture.started ◄────┤
   │                                                       mic open ├──────────────────────────┐│
   │                                                                 VAD onset (60 ms) ─┐      ││
   │                                                       ┌── TRAINEE SPEAKING ════════╧══════╪┴──── … ═══┐
   │                                                       │  pre-roll 300 ms retained         │           │
   │                                                       └───────────────────── last voiced ─┴───────────┤
   │                                                                     hangover 500–700 ms ──────────────┼──┐
   │                                                                                        capture.ended ─┴──┤
   │                                                                       assemble + FLAC (25) ──────────────┤
   │                                                                          host_request (turn N rendering) ┤
   │                                                                         rendering.emitted, score.enqueued┤
   │                                                                                                         ▼
SCORING PLANE — turn N   (starts here; runs while turn N+1 is being spoken and interpreted)
   │                                                                                          ┌ score.enqueued
   │                                                                                          ├ extractors 30 ms
   │                                                                                          ├ grader.started
   │                                                                                          ├── 2200 ms ──────►
   │                                                                                          │  (GPU leases, 25 ms
   │                                                                                          │   submissions, yields
   │                                                                                          │   whenever live_active)
   │                                                                                          └─► verdict.merged
   │                                                                                              (lands mid-turn N+1)
RUNTIME — turn N+1 source (patient, es-MX)
   │                                                                                          ├ turn.opened
   │                                                                                          ├ acquire_live()  ← grader
   │                                                                                          │                    yields
   │                                                                                          ├─ prefill … speaks …

   ▲                                                                      ▲                 ▲
   │                                                                      │                 │
   trainee hears the clinician                                            T_gap window      the grader's entire
   ~615 ms after turn.opened                                              (§3.2)            budget lives inside
                                                                                            the human's speaking time


BARGE-IN, if it happens (§9) — inserted anywhere inside SPEAKING:

        ══ c0 ══ c1 ══╗
                      ║ ← 240 ms of voiced, non-echo input detected
                      ╚═► ramp 20 ms ─► SILENT
                          │ cursor frozen: spoken_prefix_chars = 148
                          │ TTSRouter.cancel  →  host.cancel  →  tts.interrupted
                          └─► capture.started WITH 300 ms pre-roll
                              (the trainee's first syllable predates detection)
```

---

## 13. Open questions and named gaps

Stated, not papered over.

| # | Item | Status | What settles it |
|---|---|---|---|
| 1 | `heard_verbatim` fidelity — is the live model's own transcription good enough to score against, for Spanish-dominant and Mixteco-influenced speakers? | **[open]** — the largest risk in this document | Word-error-rate against hand transcripts of the 40-turn calibration audio (`SETUP.md` §6), reported in `docs/08-evals.md`. Fallback is the off-path re-transcription pass (§4) |
| 2 | Partial-chunk handling on barge-in: exclude (current) or include-and-mark-unscoreable | **[proposed]** — mirrors open item 2 in `docs/03-system-architecture.md` §16 | Trainer judgement on recorded truncated turns. If exclusion produces spurious *addition* findings, flip the rule |
| 3 | `capture.reopened` — a new event kind required by §5.4, not yet in the §10.2 catalogue of `docs/03-system-architecture.md` | **[proposed]** | Adopt in the same change that lands the endpointer. Group: Turn |
| 4 | Silero VAD as a dependency | **[decided, pending approval]** | The false-endpoint A/B against `RmsVad` (§5.1). If the delta is small, drop the dependency |
| 5 | Cough-after-barge-in: no playback resume (§9.3 last row) | **[proposed]** | Frequency in real sessions. If it is common, the fix is re-synthesis from a *chunk* boundary before `spoken_prefix_chars`, never a mid-chunk offset |
| 6 | Two agents sharing one `rehearsal-live` host: KV cache thrash when clinician and patient alternate | **[open]** | Measure prefill time for turn *N+1* when the speaker alternates vs repeats. If alternation costs > 150 ms, the fix is two persistent cache slots, not two processes |
| 7 | `resume_grace_ms` coupling to measured first-audible latency (§5.4) | **[decided]** | `rehearsal doctor` writes it into `budget.local.json`; there is a startup assertion that it is ≤ measured p50 first-audible |
| 8 | Bluetooth headsets | **[decided — unsupported for scored sessions]** | HFP mode collapses the mic to 8–16 kHz and adds 100–300 ms of uncontrolled device latency. `doctor` detects the transport and warns; wired or USB only |

**Out of scope here, for the record.** No acoustic echo cancellation (§7.2). No custom inference
server — MLX and llama.cpp are used as they ship (`docs/03-system-architecture.md` §15). No model
training, fine-tuning or adapters of any kind, including for VAD or TTS: the VAD is used
off-the-shelf and the endpointing policy above it is deterministic code, which is the whole
point.

---

## 14. Checklist before any change to this pipeline lands

- [ ] `T_gap` p50/p95 measured before and after, same machine, same scenario, n ≥ 30 turns
- [ ] The off-path assertion in §8.4 re-run (grader forced to p99 ⇒ `T_gap` p95 moves < 40 ms)
- [ ] Barge-in stop time p95 still ≤ 120 ms, measured with both TTS backends
- [ ] False-endpoint (retraction) rate reported; no silent threshold auto-tuning introduced
- [ ] `spoken_prefix_chars` still advances only at chunk boundaries (§6.4) — this is the ground-truth invariant
- [ ] Resident memory re-measured against the §10.1 table; total still leaves ≥ 20 GB headroom
- [ ] Every new stage has a `StageMark`, a row in the §3.1 budget table, and a column in `turn_timings`
- [ ] No new degradation path that is invisible to the trainee (`degraded.entered` with a numeric trigger)
