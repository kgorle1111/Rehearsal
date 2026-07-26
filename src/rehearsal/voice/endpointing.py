"""The endpointer state machine. misc/docs/05-voice-pipeline.md §5.2/§5.3/§5.4/§5.5.

Deterministic, no model involved — driven by a stream of `P(speech)` floats
(what a real `Vad.push()` would return) rather than raw audio frames, per
this workstream's hardware-independence scoping note: real Silero/RMS VAD
implementations are BLOCKED-ON-HARDWARE, but the state machine they drive is
pure logic and fully testable against synthetic input.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class EndpointPolicy:
    """misc/docs/05-voice-pipeline.md §5.2. Field set and defaults are frozen."""

    speech_threshold: float = 0.55
    silence_threshold: float = 0.35
    onset_frames: int = 3
    hangover_ms: int = 700
    hangover_short_ms: int = 1100
    hangover_long_ms: int = 500
    resume_grace_ms: int = 600
    preroll_ms: int = 300
    min_utterance_ms: int = 250
    capture_max_ms: int = 45_000


class EndpointState(Enum):
    LISTENING = "listening"
    SPEAKING = "speaking"
    HANGOVER = "hangover"
    CLOSED = "closed"


class EndpointEvent(Enum):
    ONSET = "onset"
    CAPTURE_ENDED = "capture.ended"
    CAPTURE_ENDED_TRUNCATED = "capture.ended.truncated"
    RETRACTED = "capture.reopened"


class Endpointer:
    """§5.2's state diagram plus the §5.3 adaptive-hangover branch, the §5.4
    false-endpoint retraction, and the §5.5 short/long-utterance edge cases.

    `rms` is an optional per-frame signal (synthetic in this build — no real
    audio) used only for the §5.3 "trailing energy falling" branch; when
    omitted that branch simply never fires and hangover falls through to the
    short/default rule, which is still correct, just less precise.
    """

    def __init__(self, policy: EndpointPolicy | None = None, frame_ms: int = 20) -> None:
        self.policy = policy or EndpointPolicy()
        self.frame_ms = frame_ms
        self.state = EndpointState.LISTENING
        self._voiced_run = 0
        self._utterance_ms = 0
        self._hangover_elapsed_ms = 0
        self._hangover_target_ms = self.policy.hangover_ms
        self._closed_elapsed_ms = 0
        self._rms_history: list[float] = []
        self._sticky_voiced = False

    def reset(self) -> None:
        self.state = EndpointState.LISTENING
        self._voiced_run = 0
        self._utterance_ms = 0
        self._hangover_elapsed_ms = 0
        self._hangover_target_ms = self.policy.hangover_ms
        self._closed_elapsed_ms = 0
        self._rms_history = []
        self._sticky_voiced = False

    def push(self, p_speech: float, rms: float | None = None) -> EndpointEvent | None:
        voiced = self._classify(p_speech)

        if self.state is EndpointState.LISTENING:
            return self._on_listening(voiced)
        if self.state is EndpointState.SPEAKING:
            return self._on_speaking(voiced, rms)
        if self.state is EndpointState.HANGOVER:
            return self._on_hangover(voiced, rms)
        return self._on_closed(voiced)

    def _classify(self, p: float) -> bool:
        # Hysteresis: a frame in the dead zone (silence_threshold, speech_threshold)
        # keeps whatever the last classification was.
        if p >= self.policy.speech_threshold:
            self._sticky_voiced = True
        elif p <= self.policy.silence_threshold:
            self._sticky_voiced = False
        return self._sticky_voiced

    def _on_listening(self, voiced: bool) -> EndpointEvent | None:
        if not voiced:
            self._voiced_run = 0
            return None
        self._voiced_run += 1
        if self._voiced_run < self.policy.onset_frames:
            return None
        self.state = EndpointState.SPEAKING
        self._utterance_ms = self._voiced_run * self.frame_ms
        self._rms_history = []
        return EndpointEvent.ONSET

    def _on_speaking(self, voiced: bool, rms: float | None) -> EndpointEvent | None:
        self._utterance_ms += self.frame_ms
        if rms is not None:
            self._rms_history.append(rms)
        if self._utterance_ms >= self.policy.capture_max_ms:
            self.state = EndpointState.CLOSED
            self._closed_elapsed_ms = 0
            return EndpointEvent.CAPTURE_ENDED_TRUNCATED
        if voiced:
            return None
        # Unvoiced run begins. This frame *is* the first hangover tick, not
        # a free reset to zero — silence starts counting from the frame that
        # started it.
        self.state = EndpointState.HANGOVER
        self._hangover_target_ms = self._select_hangover()
        self._hangover_elapsed_ms = 0
        return self._hangover_tick()

    def _on_hangover(self, voiced: bool, rms: float | None) -> EndpointEvent | None:
        if voiced:
            self.state = EndpointState.SPEAKING
            self._utterance_ms += self.frame_ms
            if rms is not None:
                self._rms_history.append(rms)
            return None
        return self._hangover_tick()

    def _hangover_tick(self) -> EndpointEvent | None:
        self._hangover_elapsed_ms += self.frame_ms
        if self._hangover_elapsed_ms < self._hangover_target_ms:
            return None

        # §5.5: onset present but total voiced time below the floor is a
        # cough, not a turn. Discard, no event, back to listening.
        if self._utterance_ms < self.policy.min_utterance_ms:
            self.state = EndpointState.LISTENING
            self._voiced_run = 0
            return None

        self.state = EndpointState.CLOSED
        self._closed_elapsed_ms = 0
        return EndpointEvent.CAPTURE_ENDED

    def _on_closed(self, voiced: bool) -> EndpointEvent | None:
        self._closed_elapsed_ms += self.frame_ms
        if voiced and self._closed_elapsed_ms <= self.policy.resume_grace_ms:
            # §5.4 row 1: within grace, no counterpart audio audible yet (the
            # orchestrator is responsible for that second condition — this
            # layer only knows about VAD/timing) -> retract.
            self.state = EndpointState.SPEAKING
            self._voiced_run = self.policy.onset_frames
            self._utterance_ms = 0
            self._rms_history = []
            return EndpointEvent.RETRACTED
        return None

    def _select_hangover(self) -> int:
        p = self.policy
        if self._utterance_ms < 1200:
            return p.hangover_short_ms
        if self._utterance_ms > 4000 and self._trailing_energy_falling():
            return p.hangover_long_ms
        return p.hangover_ms

    def _trailing_energy_falling(self) -> bool:
        hist = self._rms_history
        n = max(1, 400 // self.frame_ms)
        if len(hist) < n + 1:
            return False
        trailing = hist[-n:]
        mean_all = sum(hist) / len(hist)
        mean_trailing = sum(trailing) / len(trailing)
        return mean_trailing < 0.6 * mean_all
