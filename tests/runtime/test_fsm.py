"""FSM property test: no path to `complete` bypasses `review.signed`.

misc/docs/03-system-architecture.md §8.2's transition table has exactly one
row whose target is `complete` (`review` --human_confirms--> `complete`).
That is a structural property of `TRANSITIONS`, not something a code review
has to keep re-checking by hand — this test enumerates every row and proves
it, then proves it again behaviourally by walking the FSM through a full
session and asserting `complete` cannot be reached without first passing
through `review` via a `human_confirms` trigger that appends `review.signed`.
"""

from rehearsal.orchestrator.fsm import (
    PREV_DURABLE,
    TRANSITIONS,
    GuardFailed,
    InvalidTransition,
    SessionFSM,
    SessionState,
    transitions_into,
)


def test_only_one_transition_targets_complete() -> None:
    into_complete = transitions_into(SessionState.COMPLETE)
    assert len(into_complete) == 1
    t = into_complete[0]
    assert t.from_state == SessionState.REVIEW
    assert t.trigger == "human_confirms"
    assert "review.signed" in t.events


def test_no_any_live_row_targets_complete() -> None:
    # If a "pause"/"abort"/"unhandled_exception" (ANY_LIVE) row ever targeted
    # complete, that would be a silent bypass of the human gate reachable
    # from every state. Assert none does, structurally.
    for t in TRANSITIONS:
        if t.to_state == SessionState.COMPLETE:
            assert t.from_state == SessionState.REVIEW, (
                f"unexpected path to complete: {t.from_state} --{t.trigger}-->"
            )


def test_prev_durable_can_never_resolve_to_complete() -> None:
    # complete is terminal and therefore never pushed onto the durable
    # history as a "resumable" state a paused session could bounce back to
    # (once complete, sessions are immutable, per §8.1). Confirm no
    # PREV_DURABLE-targeting row originates from a state that could have
    # complete on top of its durable history stack.
    for t in TRANSITIONS:
        if t.to_state == PREV_DURABLE:
            assert t.from_state == SessionState.PAUSED


def test_walking_full_session_requires_review_signed_before_complete() -> None:
    fsm = SessionFSM()
    fsm.apply("configure")
    fsm.apply("bind_complete")
    fsm.apply("trainee_starts")
    fsm.apply("playback_complete")
    fsm.apply("speech_onset")
    fsm.apply("endpoint_detected")
    fsm.apply("graph_terminal_or_max_turns")
    fsm.apply("score_queue_drained_or_deadline")
    assert fsm.state is SessionState.REVIEW

    # complete is not reachable from review except via human_confirms.
    try:
        fsm.apply("pause")
        state_after_pause: SessionState = fsm.state
        assert state_after_pause is not SessionState.COMPLETE
        fsm.apply("resume")
    except InvalidTransition:
        pass
    state_before_confirm: SessionState = fsm.state
    assert state_before_confirm is not SessionState.COMPLETE

    fsm.apply("human_confirms")
    state_after_confirm: SessionState = fsm.state
    assert state_after_confirm is SessionState.COMPLETE


def test_abort_and_exception_never_land_on_complete() -> None:
    for trigger in ("abort", "unhandled_exception"):
        for start in SessionState:
            if start in (SessionState.COMPLETE, SessionState.ABORTED, SessionState.FAILED):
                continue
            fsm = SessionFSM(initial=start)
            t = fsm.apply(trigger)
            assert fsm.state is not SessionState.COMPLETE
            assert t.to_state is not SessionState.COMPLETE


def test_guard_failure_blocks_the_transition() -> None:
    fsm = SessionFSM()
    fsm.apply("configure")
    try:
        fsm.apply("bind_complete", guard_ok=False)
    except GuardFailed:
        pass
    else:
        raise AssertionError("expected GuardFailed")
    assert fsm.state is SessionState.CONFIGURING  # unchanged


if __name__ == "__main__":
    test_only_one_transition_targets_complete()
    test_no_any_live_row_targets_complete()
    test_prev_durable_can_never_resolve_to_complete()
    test_walking_full_session_requires_review_signed_before_complete()
    test_abort_and_exception_never_land_on_complete()
    test_guard_failure_blocks_the_transition()
    print("fsm: no path to complete bypasses review.signed -- confirmed")
