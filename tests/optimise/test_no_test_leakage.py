"""Static proof that the optimisation loop's code path never reads the sealed
TEST split. BUILD.md WS6 DoD: 'a static check that test.jsonl/seal.py's unseal
function is never imported/called anywhere in optimise/loop.py'."""

from __future__ import annotations

import ast
from pathlib import Path

_OPTIMISE_SRC = Path(__file__).resolve().parents[2] / "src" / "rehearsal" / "optimise"


def test_loop_source_never_names_the_sealed_split_or_the_unseal_guard() -> None:
    src = (_OPTIMISE_SRC / "loop.py").read_text()
    for token in ("test.jsonl", "unseal"):
        assert token not in src, f"loop.py must never reference {token!r} (TEST-split leakage)"


def test_no_module_in_optimise_package_imports_the_seal_guard() -> None:
    """Package-wide belt-and-suspenders: nothing under optimise/ may import
    the evals package's seal guard, regardless of what its docstrings say."""
    for path in _OPTIMISE_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module} if node.module else set()
            else:
                continue
            for name in names:
                assert name is None or "seal" not in name, (
                    f"{path.name} imports {name!r} — must never import the TEST-split seal guard"
                )
