"""The deterministic session orchestrator. misc/docs/03-system-architecture.md §6.1.

"The orchestrator is not a model, does not call a model to decide anything,
and contains no natural-language reasoning." What it owns: turn order,
seeds, deadlines, state transitions, persistence ordering. What it never
does: decide what a speaker says or whether a rendering was correct — those
come back through `hosts`/`audio` as opaque results it just records.

CRITICAL SCOPING NOTE: this build environment has no CoreAudio, no MLX, no
llama.cpp and no live model host process. `Clock`, `AudioIO`, `ModelHosts`,
`ScenarioBank` and `Store` are Protocols precisely so this class never knows
or cares whether it's driving real hardware or the fakes in
tests/runtime/fakes.py — see BUILD.md's scoping note for this workstream.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from rehearsal.orchestrator.eventlog import Event
from rehearsal.orchestrator.fsm import SessionFSM, SessionState
from rehearsal.orchestrator.resume import SessionView, fold, resumable_state
from rehearsal.orchestrator.scheduler import GraphNode, TurnScheduler
from rehearsal.orchestrator.seeds import derive_seed
from rehearsal.runtime.budget import TurnBudget


class Clock(Protocol):
    def now_ms(self) -> int: ...
    def mono_ms(self) -> int: ...


class AudioIO(Protocol):
    async def play(self, text: str) -> None: ...
    async def capture(self) -> str: ...


class ModelHosts(Protocol):
    async def generate_source(self, node_id: str, seed: int) -> str: ...
    async def score(self, source: str, rendering: str, seed: int) -> object: ...


class ScenarioBank(Protocol):
    def entry_node(self, scenario_id: str, seed: int) -> GraphNode: ...
    def successor(self, node: GraphNode, seed: int) -> GraphNode | None: ...


class Store(Protocol):
    def append(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, object] | None = None,
        *,
        turn_index: int | None = None,
        ts_ms: int = 0,
        mono_ms: int = 0,
    ) -> Event: ...

    def events_for(self, session_id: str) -> list[Event]: ...


@dataclass(frozen=True, slots=True)
class RunConfig:
    """Local stand-in for `src/rehearsal/config.py:SessionConfig`, which does
    not exist yet and is outside WS4's ownership (`config.py` is not in the
    voice/runtime/orchestrator/tests-runtime paths this workstream owns).
    Carries the fields the orchestrator actually consumes; swap for the real
    dataclass once it lands — same names, so the swap is a one-line import
    change, not a rewrite.
    """

    scenario_id: str
    trainee_id: str
    max_turns: int = 4
    root_seed: int | None = None


class SessionOrchestrator:
    def __init__(
        self,
        store: Store,
        hosts: ModelHosts,
        bank: ScenarioBank,
        audio: AudioIO,
        clock: Clock,
    ) -> None:
        self.store = store
        self.hosts = hosts
        self.bank = bank
        self.audio = audio
        self.clock = clock
        self.fsm = SessionFSM()
        self.scheduler = TurnScheduler(TurnBudget())

    def _append(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, object] | None = None,
        *,
        turn_index: int | None = None,
    ) -> Event:
        return self.store.append(
            session_id,
            kind,
            payload,
            turn_index=turn_index,
            ts_ms=self.clock.now_ms(),
            mono_ms=self.clock.mono_ms(),
        )

    def _view(self, session_id: str) -> SessionView:
        return fold(self.store.events_for(session_id))

    async def run(self, cfg: RunConfig, session_id: str) -> SessionState:
        root_seed = (
            cfg.root_seed if cfg.root_seed is not None else int.from_bytes(os.urandom(8), "big")
        )
        self._append(
            session_id, "session.created",
            {"trainee_id": cfg.trainee_id, "root_seed": root_seed},
        )
        self._append(session_id, "seed.drawn", {"root_seed": root_seed})
        self.fsm.apply("configure")

        entry_seed = derive_seed(root_seed, "scenario_selection", 0)
        node = self.bank.entry_node(cfg.scenario_id, entry_seed)
        self._append(session_id, "scenario.bound", {"node_id": node.node_id})
        self.fsm.apply("bind_complete")

        self.fsm.apply("trainee_starts")
        self._append(session_id, "session.started", {})

        while True:
            view = self._view(session_id)
            plan = self.scheduler.next_plan(view, node)
            if plan.turn_index >= cfg.max_turns:
                self.fsm.apply("graph_terminal_or_max_turns")
                self._append(session_id, "encounter.ended", {})
                break

            self._append(
                session_id,
                "turn.opened",
                {"turn_index": plan.turn_index, "seed": plan.seed, "node_id": plan.node_id},
                turn_index=plan.turn_index,
            )

            source_text = await self.hosts.generate_source(plan.node_id, plan.seed)
            self._append(
                session_id, "source.emitted", {"text": source_text}, turn_index=plan.turn_index
            )
            await self.audio.play(source_text)
            self.fsm.apply("playback_complete")

            self.fsm.apply("speech_onset")
            rendering = await self.audio.capture()
            self._append(session_id, "capture.ended", {}, turn_index=plan.turn_index)
            self.fsm.apply("endpoint_detected")
            self._append(
                session_id, "rendering.emitted",
                {"text": rendering}, turn_index=plan.turn_index,
            )

            # Scoring is launched, not awaited inline in the critical path in
            # the real system (§6.2's overlap); here it is awaited directly
            # since there is no real host process to overlap against — see
            # tests/runtime/test_scheduler.py for the ordering property this
            # scoping note stands in for.
            await self.hosts.score(source_text, rendering, plan.seed)

            next_index = plan.turn_index + 1
            next_node = self.bank.successor(node, derive_seed(root_seed, "graph_walk", next_index))
            if next_node is None or next_index >= cfg.max_turns:
                self.fsm.apply("graph_terminal_or_max_turns")
                self._append(session_id, "encounter.ended", {})
                break
            node = next_node
            self.fsm.apply("graph_has_next_and_under_max_turns")

        self.fsm.apply("score_queue_drained_or_deadline")
        self._append(session_id, "report.assembled", {})
        return self.fsm.state

    async def confirm_review(self, session_id: str, reviewer: str) -> SessionState:
        self.fsm.apply("human_confirms")
        self._append(session_id, "review.signed", {"reviewer": reviewer})
        return self.fsm.state

    async def resume(self, session_id: str) -> SessionState:
        view = self._view(session_id)
        outcome = resumable_state(view)
        self.fsm.reset_to(outcome.state)
        if outcome.turn_abandoned:
            self._append(
                session_id,
                "turn.abandoned",
                {"turn_index": outcome.reopen_turn_index, "seed": outcome.reopen_seed},
                turn_index=outcome.reopen_turn_index,
            )
        return self.fsm.state

    async def abort(self, session_id: str, reason: str) -> None:
        self.fsm.apply("abort")
        self._append(session_id, "session.aborted", {"reason": reason})
