"""Mechanical enforcement of information isolation. misc/docs/15-workstreams.md §4.

`runtime/` (and, by the same logic, `orchestrator/` and `voice/`, since they
sit on the same side of the isolation boundary) must never import from
`rehearsal.scoring`. This is a static grep check, not a runtime assertion,
so it catches the import even if the code path that would exercise it is
never called in a test.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "rehearsal"
CHECKED_DIRS = ("runtime", "orchestrator", "voice")
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+rehearsal\.scoring\b", re.MULTILINE)


def test_no_ws4_module_imports_scoring() -> None:
    offenders = []
    for dirname in CHECKED_DIRS:
        for path in (ROOT / dirname).rglob("*.py"):
            text = path.read_text()
            if IMPORT_RE.search(text):
                offenders.append(str(path))
    assert not offenders, f"forbidden import of rehearsal.scoring in: {offenders}"


if __name__ == "__main__":
    test_no_ws4_module_imports_scoring()
    print("import ban: rehearsal.scoring is not imported anywhere in voice/runtime/orchestrator")
