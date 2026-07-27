"""Shared pytest fixtures used across multiple workstreams' test suites.

Per BUILD.md WS-TEST scope: this file holds only fixtures that are actually
reused by more than one test module. It is not a place to pre-build fixtures
for code that does not exist yet.

--------------------------------------------------------------------------
Flaky-test policy
--------------------------------------------------------------------------
- No `time.sleep`-based tests anywhere in this repo. Anything that needs
  time to move uses an injectable clock (see WS4's `LogicalClock` in
  `tests/runtime/fakes.py`) — never a real sleep on the wall clock.
- No test may depend on wall-clock timing, thread/process scheduling order,
  or network access. `score_turn`, extractors, the FSM, and the event log
  are all pure with respect to their inputs; a test that needs a retry to
  pass is testing the wrong thing.
- A test that fails intermittently is filed as a bug, not retried into
  green. Quarantine it (skip with a reason citing the bug) and fix the root
  cause in the owning workstream — never paper over it with `@retry` or a
  re-run loop.
- Hypothesis-based tests (if any workstream adds them) must run under a
  derandomized profile so a red run is reproducible byte-for-byte, not a
  coin flip that happens to land differently in CI.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from rehearsal.contracts import Direction, ScenarioRecord, TurnRecord
from rehearsal.scenarios.bank import ScenarioProvenance, load_scenario_file

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_SCENARIOS_DIR = REPO_ROOT / "data" / "scenarios"


@pytest.fixture
def seed_scenarios_dir() -> Path:
    """The directory WS7's real seed scenarios live in. Reused by WS7's own
    bank tests and by cross-workstream contract tests that need a real
    (not fabricated) `ScenarioRecord`."""
    return SEED_SCENARIOS_DIR


@pytest.fixture
def load_seed_scenario() -> Callable[[str], tuple[ScenarioRecord, ScenarioProvenance]]:
    """Load one of WS7's seed scenarios by file stem, e.g.
    ``load_seed_scenario("sc_0001_dm2_metformin_counseling")``.

    Thin wrapper around WS7's own `load_scenario_file` — kept here because
    both WS3-adjacent tests (persona) and WS-TEST's contract tests need to
    load a real scenario by name, and the path-joining is the part worth
    sharing, not the parsing (which stays WS7's).
    """

    def _load(stem: str) -> tuple[ScenarioRecord, ScenarioProvenance]:
        return load_scenario_file(SEED_SCENARIOS_DIR / f"{stem}.json")

    return _load


@pytest.fixture
def make_turn_record() -> Callable[..., TurnRecord]:
    """Build a `contracts.TurnRecord` with sensible defaults, overriding only
    what a test cares about. Generalises the `_turn()` helper duplicated in
    `tests/scoring/test_engine.py` so cross-workstream contract tests don't
    hand-roll a fourth copy of it."""

    def _make(
        source_utterance: str,
        rendering_transcript: str,
        *,
        direction: Direction = Direction.EN_TO_ES,
        turn_id: str = "t1",
        session_id: str = "s1",
    ) -> TurnRecord:
        source_lang = "en" if direction is Direction.EN_TO_ES else "es"
        return TurnRecord(
            turn_id=turn_id,
            session_id=session_id,
            direction=direction,
            source_utterance=source_utterance,
            source_lang=source_lang,
            rendering_transcript=rendering_transcript,
        )

    return _make
