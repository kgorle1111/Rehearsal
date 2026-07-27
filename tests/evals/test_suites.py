"""Every suite returns a well-formed EvalResult. misc/docs/08-evals.md §2.2 DoD.

EV-00 is checked for a real 1.00 conformance number; the rest are checked
for a well-formed SKIPPED/REPORT_ONLY result, and the human-blocked ones for
the BLOCKED-ON-HUMAN string that must never silently disappear.
"""

from __future__ import annotations

import importlib

import pytest

from rehearsal.evals.result import EvalConfig, EvalResult, GateOutcome

SUITE_MODULES = [
    "rehearsal.evals.suites.ev00_extractors",
    "rehearsal.evals.suites.ev01_calibration",
    "rehearsal.evals.suites.ev02_critical_recall",
    "rehearsal.evals.suites.ev03_human_ceiling",
    "rehearsal.evals.suites.ev05_leakage",
    "rehearsal.evals.suites.ev07_latency",
    "rehearsal.evals.suites.ev08_session",
]

BLOCKED_ON_HUMAN_MODULES = [
    "rehearsal.evals.suites.ev01_calibration",
    "rehearsal.evals.suites.ev02_critical_recall",
    "rehearsal.evals.suites.ev03_human_ceiling",
]


@pytest.mark.parametrize("module_name", SUITE_MODULES)
def test_every_suite_returns_a_well_formed_eval_result(module_name: str) -> None:
    module = importlib.import_module(module_name)
    result = module.run(EvalConfig())
    assert result is not None
    assert isinstance(result, EvalResult)
    assert result.eval_id
    assert isinstance(result.gate, GateOutcome)
    assert result.notes  # never silently absent


@pytest.mark.parametrize("module_name", BLOCKED_ON_HUMAN_MODULES)
def test_human_blocked_suites_say_so_explicitly(module_name: str) -> None:
    module = importlib.import_module(module_name)
    result = module.run(EvalConfig())
    assert result.gate == GateOutcome.SKIPPED
    assert "BLOCKED-ON-HUMAN" in result.notes


def test_ev00_reports_extractor_conformance_1_00() -> None:
    module = importlib.import_module("rehearsal.evals.suites.ev00_extractors")
    result = module.run(EvalConfig())
    assert result.metrics["extractor_conformance"] == 1.00
    assert result.gate == GateOutcome.PASS
    assert result.n > 0
