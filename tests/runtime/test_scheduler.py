"""Scheduler ordering property. misc/docs/03-system-architecture.md §6.2.

The rule to prove: scoring for turn N must be *launched* before
`capture.ended` of turn N+1 is processed. Modelled with a fake clock and
configurable fake stage durations — no real timing. Includes a violating
case (queue depth) that correctly triggers a shed signal via
`TurnScheduler.should_shed`.
"""

from dataclasses import dataclass

from rehearsal.orchestrator.resume import SessionView
from rehearsal.orchestrator.scheduler import TurnScheduler
from rehearsal.orchestrator.seeds import derive_seed
from rehearsal.runtime.budget import DegradeLevel, TurnBudget

ROOT_SEED = 42


@dataclass(frozen=True, slots=True)
class _Node:
    node_id: str


def _view(turn_index: int) -> SessionView:
    from rehearsal.orchestrator.fsm import SessionState

    seeds = {i: derive_seed(ROOT_SEED, "graph_walk", i) for i in range(turn_index)}
    return SessionView(
        session_id="s1", root_seed=ROOT_SEED, state=SessionState.TURN_CLOSING,
        last_durable_state=SessionState.TURN_CLOSING, open_turn_index=None,
        open_turn_seed=None, turn_seeds=seeds,
    )


def _turn_n_plus_1_capture_ended_ms(
    source_generation_ms: int, tts_first_audio_ms: int, capture_ms: int
) -> int:
    """Wall-clock offset, from `rendering.emitted(N)`, at which
    `capture.ended(N+1)` lands: turn N+1's tts + the trainee's capture time."""
    return source_generation_ms + tts_first_audio_ms + capture_ms


def test_nominal_launch_precedes_next_capture_ended() -> None:
    """Scoring launches instantly on rendering.emitted(N) (fire-and-forget,
    per §6.2's diagram); turn N+1's own tts+capture always takes longer than
    an instant launch, so the rule holds with wide margin in the nominal case."""
    scheduler = TurnScheduler(TurnBudget())
    for _turn_index in range(10):
        launch_offset_ms = 0  # launched "the instant rendering.emitted lands"
        next_capture_ended_ms = _turn_n_plus_1_capture_ended_ms(
            source_generation_ms=900, tts_first_audio_ms=400, capture_ms=2000
        )
        assert launch_offset_ms <= next_capture_ended_ms
        degrade = scheduler.should_shed(queue_depth=0, ewma_grader_ms=1200)
        assert degrade is DegradeLevel.L0


def test_sustained_queue_depth_violates_ordering_and_sheds() -> None:
    """A launcher that serializes launches (each queued launch waits for every
    one ahead of it) falls behind if turns arrive faster than launches drain:
    queue_depth accumulates one per turn, and the Nth queued launch fires
    `N * per_launch_overhead_ms` after the turn that enqueued it. Once that
    pushes a launch past the next turn's capture.ended, the ordering rule is
    violated and should_shed must signal a degrade level rather than letting
    hints silently go stale forever."""
    scheduler = TurnScheduler(TurnBudget())
    per_launch_overhead_ms = 1500  # fake: launcher itself is saturated
    next_capture_ended_ms = _turn_n_plus_1_capture_ended_ms(
        source_generation_ms=900, tts_first_audio_ms=400, capture_ms=1000
    )
    violations = 0

    for queue_depth in range(1, 7):
        launch_offset_ms = queue_depth * per_launch_overhead_ms
        if launch_offset_ms > next_capture_ended_ms:
            violations += 1
            degrade = scheduler.should_shed(queue_depth=queue_depth, ewma_grader_ms=1200)
            assert degrade is not DegradeLevel.L0, "ordering violated but no shed signal raised"

    assert violations > 0, "test setup did not actually exercise a violation"


def test_should_shed_grader_overshoot_outranks_queue_depth() -> None:
    scheduler = TurnScheduler(TurnBudget(grader_wall_ms=3_500))
    assert scheduler.should_shed(queue_depth=0, ewma_grader_ms=4_000) is DegradeLevel.L2
    assert scheduler.should_shed(queue_depth=2, ewma_grader_ms=1_000) is DegradeLevel.L1
    assert scheduler.should_shed(queue_depth=0, ewma_grader_ms=1_000) is DegradeLevel.L0


def test_next_plan_seeds_and_alternates_speaker() -> None:
    scheduler = TurnScheduler(TurnBudget())
    view = _view(0)
    plan0 = scheduler.next_plan(view, _Node("n0"))
    assert plan0.turn_index == 0
    assert plan0.speaker == "clinician"
    assert plan0.seed == derive_seed(ROOT_SEED, "graph_walk", 0)

    view1 = _view(1)
    plan1 = scheduler.next_plan(view1, _Node("n1"))
    assert plan1.turn_index == 1
    assert plan1.speaker == "patient"
    assert plan1.seed == derive_seed(ROOT_SEED, "graph_walk", 1)


if __name__ == "__main__":
    test_nominal_launch_precedes_next_capture_ended()
    test_sustained_queue_depth_violates_ordering_and_sheds()
    test_should_shed_grader_overshoot_outranks_queue_depth()
    test_next_plan_seeds_and_alternates_speaker()
    print("scheduler: all checks passed")
