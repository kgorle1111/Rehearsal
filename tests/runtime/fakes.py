"""In-memory fakes for SessionOrchestrator's injected Protocols.

Same DI pattern WS1 used for its grader stub (BUILD.md): fake implementations
that satisfy the Protocols in `rehearsal.orchestrator.loop` so the
orchestrator can be exercised end-to-end without real audio hardware or a
live model host process.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rehearsal.orchestrator.scheduler import GraphNode


@dataclass
class LogicalClock:
    """Deterministic, injectable clock. `advance` is the only way time moves."""

    _now_ms: int = 0
    _mono_ms: int = 0

    def now_ms(self) -> int:
        return self._now_ms

    def mono_ms(self) -> int:
        return self._mono_ms

    def advance(self, ms: int) -> None:
        self._now_ms += ms
        self._mono_ms += ms


@dataclass
class FakeAudioIO:
    """Returns canned renderings in order; records what it was asked to play."""

    renderings: list[str] = field(default_factory=lambda: ["fake rendering"])
    played: list[str] = field(default_factory=list)
    _i: int = 0

    async def play(self, text: str) -> None:
        self.played.append(text)

    async def capture(self) -> str:
        text = self.renderings[self._i % len(self.renderings)]
        self._i += 1
        return text


@dataclass
class FakeModelHosts:
    """Canned source text; scoring is a no-op that just records the call."""

    source_text: str = "fake source utterance"
    scored: list[tuple[str, str, int]] = field(default_factory=list)

    async def generate_source(self, node_id: str, seed: int) -> str:
        return f"{self.source_text} ({node_id}/{seed})"

    async def score(self, source: str, rendering: str, seed: int) -> object:
        self.scored.append((source, rendering, seed))
        return None


@dataclass(frozen=True, slots=True)
class FakeNode:
    node_id: str


@dataclass
class FakeScenarioBank:
    """A trivial straight-line graph of `n_nodes` nodes."""

    n_nodes: int = 8

    def entry_node(self, scenario_id: str, seed: int) -> FakeNode:
        return FakeNode(node_id=f"{scenario_id}:0")

    def successor(self, node: GraphNode, seed: int) -> FakeNode | None:
        idx = int(node.node_id.rsplit(":", 1)[-1]) + 1
        if idx >= self.n_nodes:
            return None
        scenario_id = node.node_id.rsplit(":", 1)[0]
        return FakeNode(node_id=f"{scenario_id}:{idx}")
