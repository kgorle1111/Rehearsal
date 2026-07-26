"""The session state machine. misc/docs/03-system-architecture.md §8.1/§8.2.

States and transitions use the doc's authoritative names, not BUILD.md's
shorthand paraphrase. The whole point of encoding this as a data table (not
a pile of `if` statements) is that the "no path to `complete` bypasses human
review" invariant becomes a structural property of `TRANSITIONS` that a test
can check by inspection, rather than something someone has to remember to
preserve while editing branches.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class SessionState(Enum):
    INIT = "init"
    CONFIGURING = "configuring"
    ARMED = "armed"
    SOURCE_SPEAKING = "source_speaking"
    AWAITING_RENDERING = "awaiting_rendering"
    RENDERING_CAPTURING = "rendering_capturing"
    TURN_CLOSING = "turn_closing"
    PAUSED = "paused"
    RECOVERING = "recovering"
    DEBRIEF = "debrief"
    REVIEW = "review"
    COMPLETE = "complete"
    ABORTED = "aborted"
    FAILED = "failed"


# Durable checkpoint states, per §8.1's "Durable checkpoint?" column.
# source_speaking, rendering_capturing: No. recovering: transient/derived.
DURABLE: Final[frozenset[SessionState]] = frozenset(
    {
        SessionState.INIT,
        SessionState.CONFIGURING,
        SessionState.ARMED,
        SessionState.AWAITING_RENDERING,
        SessionState.TURN_CLOSING,
        SessionState.PAUSED,
        SessionState.DEBRIEF,
        SessionState.REVIEW,
        SessionState.COMPLETE,
        SessionState.ABORTED,
        SessionState.FAILED,
    }
)

TERMINAL: Final[frozenset[SessionState]] = frozenset(
    {SessionState.COMPLETE, SessionState.ABORTED, SessionState.FAILED}
)

# Sentinels used only inside the transition table.
ANY_LIVE: Final[str] = "ANY_LIVE"  # from_state: matches any non-terminal state
PREV_DURABLE: Final[str] = "PREV_DURABLE"  # to_state: resolved at apply-time


@dataclass(frozen=True, slots=True)
class Transition:
    from_state: SessionState | str
    trigger: str
    to_state: SessionState | str
    guard: str | None = None
    events: tuple[str, ...] = ()


# misc/docs/03-system-architecture.md §8.2, one row per table row (the "any
# live state" and "paused -> previous durable state" rows use the sentinels
# above rather than being expanded per-state, which would just be the same
# eleven rows repeated with no behavioural difference).
TRANSITIONS: Final[tuple[Transition, ...]] = (
    Transition(
        SessionState.INIT, "configure", SessionState.CONFIGURING,
        guard="scenario_exists_and_hosts_healthy", events=("session.created", "seed.drawn"),
    ),
    Transition(
        SessionState.CONFIGURING, "bind_complete", SessionState.ARMED,
        guard="graph_entry_resolved", events=("scenario.bound",),
    ),
    Transition(
        SessionState.CONFIGURING, "host_probe_fails", SessionState.FAILED,
        events=("session.failed",),
    ),
    Transition(
        SessionState.ARMED, "trainee_starts", SessionState.SOURCE_SPEAKING,
        guard="audio_device_present", events=("session.started", "turn.opened"),
    ),
    Transition(
        SessionState.SOURCE_SPEAKING, "first_pcm_frame", SessionState.SOURCE_SPEAKING,
        guard="within_tts_first_audio_ms", events=("tts.started",),
    ),
    Transition(
        SessionState.SOURCE_SPEAKING, "playback_complete", SessionState.AWAITING_RENDERING,
        events=("tts.finished", "capture.started"),
    ),
    Transition(
        SessionState.SOURCE_SPEAKING, "trainee_speaks_over_playback",
        SessionState.RENDERING_CAPTURING,
        guard="barge_in_enabled", events=("tts.interrupted",),
    ),
    Transition(
        SessionState.AWAITING_RENDERING, "speech_onset", SessionState.RENDERING_CAPTURING,
    ),
    Transition(
        SessionState.AWAITING_RENDERING, "silence_exceeds_capture_max", SessionState.TURN_CLOSING,
        events=("rendering.emitted",),
    ),
    Transition(
        SessionState.RENDERING_CAPTURING, "endpoint_detected", SessionState.TURN_CLOSING,
        events=("capture.ended", "rendering.emitted"),
    ),
    Transition(
        SessionState.RENDERING_CAPTURING, "device_lost", SessionState.PAUSED,
        events=("capture_lost",),
    ),
    Transition(
        SessionState.TURN_CLOSING, "graph_has_next_and_under_max_turns",
        SessionState.SOURCE_SPEAKING,
        events=("turn.opened",),
    ),
    Transition(
        SessionState.TURN_CLOSING, "graph_terminal_or_max_turns", SessionState.DEBRIEF,
        events=("encounter.ended",),
    ),
    Transition(ANY_LIVE, "pause", SessionState.PAUSED, events=("session.paused",)),
    Transition(
        SessionState.PAUSED, "resume", PREV_DURABLE,
        guard="hosts_healthy_and_device_present", events=("session.resumed",),
    ),
    Transition(
        SessionState.PAUSED, "device_recovery_elapsed_unrecoverable", SessionState.ABORTED,
        events=("session.aborted",),
    ),
    Transition(ANY_LIVE, "abort", SessionState.ABORTED, events=("session.aborted",)),
    Transition(ANY_LIVE, "unhandled_exception", SessionState.FAILED, events=("session.failed",)),
    Transition(
        SessionState.DEBRIEF, "score_queue_drained_or_deadline", SessionState.REVIEW,
        events=("report.assembled",),
    ),
    Transition(
        SessionState.REVIEW, "human_confirms", SessionState.COMPLETE,
        events=("review.signed",),
    ),
    Transition(
        SessionState.REVIEW, "human_overrides_finding", SessionState.REVIEW,
        events=("review.override",),
    ),
)

# Event kind -> the durable state it checkpoints, per §8.2's side-effects
# column. Used by resume.fold to reconstruct a SessionView from a raw event
# list without re-deriving the whole transition table.
EVENT_KIND_TO_DURABLE_STATE: Final[dict[str, SessionState]] = {
    "session.created": SessionState.INIT,
    "scenario.bound": SessionState.ARMED,
    "capture.started": SessionState.AWAITING_RENDERING,
    "rendering.emitted": SessionState.TURN_CLOSING,
    "session.paused": SessionState.PAUSED,
    "encounter.ended": SessionState.DEBRIEF,
    "report.assembled": SessionState.REVIEW,
    "review.signed": SessionState.COMPLETE,
    "session.aborted": SessionState.ABORTED,
    "session.failed": SessionState.FAILED,
}


class InvalidTransition(RuntimeError):
    pass


class GuardFailed(RuntimeError):
    pass


class SessionFSM:
    """A typed, testable state machine. No model, no I/O — matches
    misc/docs/03-system-architecture.md §6's "the orchestrator contains no
    natural-language reasoning" requirement by construction: it only looks up
    rows in `TRANSITIONS`.
    """

    def __init__(self, initial: SessionState = SessionState.INIT) -> None:
        self.state = initial
        self._durable_history: list[SessionState] = [initial] if initial in DURABLE else []

    def reset_to(self, state: SessionState) -> None:
        """Used by crash-resume to seed the FSM at a folded state without
        replaying every transition that produced it."""
        self.state = state
        self._durable_history = [state] if state in DURABLE else []

    def apply(self, trigger: str, *, guard_ok: bool = True) -> Transition:
        t = self._match(trigger)
        if t.guard is not None and not guard_ok:
            raise GuardFailed(f"{self.state} --{trigger}--> guard {t.guard!r} failed")

        to = t.to_state
        if to == PREV_DURABLE:
            if not self._durable_history:
                raise InvalidTransition("paused with no prior durable state to resume to")
            to = self._durable_history[-1]
        assert isinstance(to, SessionState)

        self.state = to
        # PAUSED is itself a durable checkpoint (§8.1: crash-resume can land
        # there directly), but "paused -> resume -> previous durable state"
        # (§8.2) means the state the session was *in before pausing* — so
        # PAUSED never becomes its own resume target on this stack.
        if to in DURABLE and to is not SessionState.PAUSED:
            if not self._durable_history or self._durable_history[-1] != to:
                self._durable_history.append(to)
        return t

    def _match(self, trigger: str) -> Transition:
        for t in TRANSITIONS:
            if t.from_state == self.state and t.trigger == trigger:
                return t
        if self.state not in TERMINAL:
            for t in TRANSITIONS:
                if t.from_state == ANY_LIVE and t.trigger == trigger:
                    return t
        raise InvalidTransition(f"no transition from {self.state} on {trigger!r}")


def transitions_into(state: SessionState) -> tuple[Transition, ...]:
    """All table rows whose *resolved* target is `state`. `PREV_DURABLE` never
    resolves to `state` here since it's dynamic, not `state` unless `state`
    happens to be reached that way at runtime — which the FSM property test
    below (see tests/runtime/test_fsm.py) checks separately."""
    return tuple(t for t in TRANSITIONS if t.to_state == state)
