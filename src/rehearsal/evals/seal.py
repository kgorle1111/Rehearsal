"""The deterministic guard on the sealed TEST split. misc/docs/08-evals.md §5.

`load_test_split()` refuses to read `data/calibration/test.jsonl` unless the
process called `unseal(reason)` first. There is no other path in — the
mechanism, not developer discipline, is what makes DEV/TEST hold at 2am
(§5 rule 3). The guard is provably correct regardless of whether TEST data
exists yet; it does today not (see data/calibration/README.md), and that is
a separate, honest fact from whether the guard works.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

TEST_PATH = Path("data/calibration/test.jsonl")
ACCESS_LOG = Path("data/calibration/TEST_ACCESS.log")


class SealedSplitError(RuntimeError):
    """Raised when TEST is read without an unseal() call in this process."""


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


class _UnsealState:
    """Process-local unseal token. Not persisted — every process must call
    unseal() itself; nothing carries the door open across runs."""

    def __init__(self) -> None:
        self._reason: str | None = None

    def open(self, reason: str) -> None:
        if not reason or not reason.strip():
            raise ValueError("unseal reason must be a non-empty string")
        ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ACCESS_LOG.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "reason": reason,
                        "git_commit": _git_commit(),
                    }
                )
                + "\n"
            )
        self._reason = reason  # set last: a failed log write must not open the seal

    @property
    def is_open(self) -> bool:
        return self._reason is not None


_state = _UnsealState()


def unseal(reason: str) -> None:
    """The only path that permits TEST access in this process. Appends the
    reason and the git commit to TEST_ACCESS.log (append-only in effect —
    nothing in this module ever opens the log for anything but append).
    """
    _state.open(reason)


def load_test_split() -> list[dict[str, Any]]:
    """Load data/calibration/test.jsonl.

    Raises SealedSplitError unless unseal() was called first in this
    process — never returns partial or empty data as a silent fallback for
    a missing unseal. An empty/absent file after a *successful* unseal is a
    different, honest fact (no TEST data has been labelled yet) and returns [].
    """
    if not _state.is_open:
        raise SealedSplitError(
            "TEST split is sealed — call rehearsal.evals.seal.unseal(reason) first "
            "(misc/docs/08-evals.md §5 rule 3)"
        )
    if not TEST_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    with TEST_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
