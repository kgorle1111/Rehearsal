"""SessionOrchestrator integration test, fully on fakes — no hardware.

Proves the wiring (FSM + EventLog + scheduler + resume) works together end
to end: a full synthetic session runs from `init` to `review`, requires an
explicit `confirm_review` to reach `complete`, and a crash mid-session
resumes to the correct abandoned turn.
"""

import asyncio

from rehearsal.orchestrator.eventlog import EventLog
from rehearsal.orchestrator.fsm import SessionState
from rehearsal.orchestrator.loop import RunConfig, SessionOrchestrator
from tests.runtime.fakes import FakeAudioIO, FakeModelHosts, FakeScenarioBank, LogicalClock


def _orchestrator(store: EventLog) -> SessionOrchestrator:
    return SessionOrchestrator(
        store=store,
        hosts=FakeModelHosts(),
        bank=FakeScenarioBank(n_nodes=3),
        audio=FakeAudioIO(),
        clock=LogicalClock(),
    )


def test_full_session_reaches_review_then_complete_only_on_confirm() -> None:
    store = EventLog()
    orch = _orchestrator(store)
    cfg = RunConfig(scenario_id="scn1", trainee_id="t1", max_turns=3, root_seed=1)

    end_state = asyncio.run(orch.run(cfg, "ses_1"))
    assert end_state is SessionState.REVIEW

    kinds = [e.kind for e in store.events_for("ses_1")]
    assert kinds.count("turn.opened") == 3
    assert kinds.count("rendering.emitted") == 3
    assert "review.signed" not in kinds

    final_state = asyncio.run(orch.confirm_review("ses_1", reviewer="trainee"))
    assert final_state is SessionState.COMPLETE
    assert "review.signed" in [e.kind for e in store.events_for("ses_1")]
    assert store.verify("ses_1") is True


def test_resume_after_mid_turn_crash_reopens_same_turn_and_seed() -> None:
    store = EventLog()
    clock = LogicalClock()
    orch = SessionOrchestrator(
        store=store, hosts=FakeModelHosts(), bank=FakeScenarioBank(n_nodes=5),
        audio=FakeAudioIO(), clock=clock,
    )
    store.append("ses_2", "session.created", {"trainee_id": "t1", "root_seed": 999})
    store.append("ses_2", "scenario.bound", {"node_id": "n0"})
    from rehearsal.orchestrator.seeds import derive_seed

    seed0 = derive_seed(999, "graph_walk", 0)
    seed1 = derive_seed(999, "graph_walk", 1)
    store.append(
        "ses_2", "turn.opened",
        {"turn_index": 0, "seed": seed0, "node_id": "n0"}, turn_index=0,
    )
    store.append("ses_2", "rendering.emitted", {"text": "x"}, turn_index=0)
    # turn 1 crashes mid-flight: opened, never closed.
    store.append(
        "ses_2", "turn.opened",
        {"turn_index": 1, "seed": seed1, "node_id": "n1"}, turn_index=1,
    )

    resumed_state = asyncio.run(orch.resume("ses_2"))
    assert resumed_state is SessionState.TURN_CLOSING  # last durable checkpoint pre-crash

    abandoned = [e for e in store.events_for("ses_2") if e.kind == "turn.abandoned"]
    assert len(abandoned) == 1
    assert abandoned[0].payload["turn_index"] == 1
    assert abandoned[0].payload["seed"] == seed1


def test_abort_lands_in_aborted_with_reason() -> None:
    store = EventLog()
    orch = _orchestrator(store)
    cfg = RunConfig(scenario_id="scn1", trainee_id="t1", max_turns=1, root_seed=1)
    asyncio.run(orch.run(cfg, "ses_3"))
    asyncio.run(orch.abort("ses_3", reason="user"))
    assert orch.fsm.state is SessionState.ABORTED
    last = store.events_for("ses_3")[-1]
    assert last.kind == "session.aborted"
    assert last.payload["reason"] == "user"


if __name__ == "__main__":
    test_full_session_reaches_review_then_complete_only_on_confirm()
    test_resume_after_mid_turn_crash_reopens_same_turn_and_seed()
    test_abort_lands_in_aborted_with_reason()
    print("loop: all checks passed")
