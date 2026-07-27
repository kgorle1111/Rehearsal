"""Static no-egress gate for the core loop (WS-OPS, misc/docs/13-deployment-ops.md §6).

The offline promise (§10 of the same doc) has no real "run in a
network-isolated container" test yet (stage 10, `offline-install`, is not
built — no bundle exists to install). This is the cheap static substitute:
grep the packages that make up the deterministic core loop for
network-call patterns and fail if any show up. `api`/`store` were added by
the WS-API contract-test pass (see NOT-BUILT-YET.md P5) to close the "no
network egress in the core loop (boundary test)" item in that workstream's
DoD — the API layer proxies requests to `SessionRuntime`/the SQLite store
and must stay just as offline-safe as the scoring/orchestrator core it
wraps.

`src/rehearsal/hosts/` is excluded on purpose, not by oversight.
`hosts/ollama.py` (commit 536fbcb, see NOT-BUILT-YET.md P-extra) is a real
network client to a local Ollama server, landed out-of-band and not yet
gate-checked by any workstream. It is explicitly a live-model host seam,
not part of the deterministic core, so it is excluded here rather than
silently making the whole check pass by narrowing the pattern list for
everyone. It is flagged again below via `HOSTS_EXCEPTION` and belongs on the
P5 review gate's list, not fixed ad hoc by this test.
"""

from __future__ import annotations

import re
from pathlib import Path

CORE_PACKAGES = ["scoring", "runtime", "orchestrator", "agents", "api", "store"]

NETWORK_PATTERNS = [
    r"\brequests\.",
    r"\bhttpx\.",
    r"urllib\.request",
    r"socket\.connect",
    r"socket\.create_connection",
]

HOSTS_EXCEPTION = (
    "src/rehearsal/hosts/ollama.py makes real network calls to a local Ollama "
    "server (urllib.request) — out-of-scope commit 536fbcb, not yet reviewed. "
    "See NOT-BUILT-YET.md P-extra. Deliberately excluded from this check."
)

_PATTERN = re.compile("|".join(NETWORK_PATTERNS))


def _core_source_files() -> list[Path]:
    src_root = Path(__file__).resolve().parent.parent / "src" / "rehearsal"
    files: list[Path] = []
    for pkg in CORE_PACKAGES:
        files.extend((src_root / pkg).rglob("*.py"))
    return files


def test_core_loop_has_no_network_egress_calls() -> None:
    offenders = {}
    for path in _core_source_files():
        text = path.read_text()
        hits = _PATTERN.findall(text)
        if hits:
            offenders[str(path)] = hits

    assert not offenders, (
        f"Network call patterns found in core-loop packages {CORE_PACKAGES}: {offenders}. "
        f"The core loop (scoring/runtime/orchestrator/agents) must stay offline-safe. "
        f"({HOSTS_EXCEPTION})"
    )


if __name__ == "__main__":
    test_core_loop_has_no_network_egress_calls()
    print("OK: no network egress found in", CORE_PACKAGES)
    print("Excluded by design:", HOSTS_EXCEPTION)
