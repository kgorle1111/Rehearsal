"""seal.py — the TEST-split guard. misc/docs/08-evals.md §5.

Proves the mechanism, not the data: TEST_PATH need not exist for these
tests to be meaningful, since the guard must refuse access before it ever
looks at the file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rehearsal.evals import seal


def _fresh_state() -> None:
    # Reset the process-local singleton so tests are order-independent —
    # each test starts as if no unseal() has happened yet in this process.
    seal._state = seal._UnsealState()


def test_load_test_split_raises_without_unseal() -> None:
    _fresh_state()
    with pytest.raises(seal.SealedSplitError):
        seal.load_test_split()


def test_unseal_requires_nonempty_reason() -> None:
    _fresh_state()
    with pytest.raises(ValueError):
        seal.unseal("")
    with pytest.raises(ValueError):
        seal.unseal("   ")


def test_unseal_then_load_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fresh_state()
    log_path = tmp_path / "TEST_ACCESS.log"
    monkeypatch.setattr(seal, "TEST_PATH", tmp_path / "test.jsonl")  # absent -> []
    monkeypatch.setattr(seal, "ACCESS_LOG", log_path)

    seal.unseal("verifying seal.py for WS9 DoD")
    assert seal.load_test_split() == []
    assert log_path.exists()
    logged = log_path.read_text(encoding="utf-8")
    assert "verifying seal.py for WS9 DoD" in logged


def test_unseal_appends_to_access_log_without_truncating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fresh_state()
    log_path = tmp_path / "TEST_ACCESS.log"
    monkeypatch.setattr(seal, "ACCESS_LOG", log_path)

    seal.unseal("first reason")
    _fresh_state()
    seal.unseal("second reason")

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
