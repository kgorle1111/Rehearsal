"""EV-00 — deterministic extractor conformance. misc/docs/08-evals.md §4.1.

Exact-match accuracy of the seven implemented extractors against the fixture
grid in `data/fixtures/extractors/*.jsonl`. Gate: extractor_conformance = 1.00,
no exceptions (`docs/06-scoring-engine.md` §4.10 excludes `temporal`, which is
not implemented).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from rehearsal.scoring.extractors import allergy, dosage, entities, frequency, laterality, numbers
from rehearsal.scoring.extractors import negation as negation_mod

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "extractors"

_TO_DICT: dict[str, Any] = {
    "numbers": numbers.to_dict,
    "dosage": dosage.to_dict,
    "frequency": frequency.to_dict,
    "laterality": laterality.to_dict,
    "allergy": allergy.to_dict,
    "entities": entities.to_dict,
    "negation": negation_mod.to_dict,
}


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _run_one(extractor_name: str, row: dict[str, Any]) -> list[dict[str, object]]:
    text: str = row["text"]
    lang = cast(Literal["en", "es"], row["lang"])
    to_dict = _TO_DICT[extractor_name]
    results: Any
    if extractor_name == "negation":
        targets = tuple(row["targets"])
        results = negation_mod.check_targets(text, lang, targets)
    elif extractor_name == "numbers":
        results = numbers.extract(text, lang)
    elif extractor_name == "dosage":
        results = dosage.extract(text, lang)
    elif extractor_name == "frequency":
        results = frequency.extract(text, lang)
    elif extractor_name == "laterality":
        results = laterality.extract(text, lang)
    elif extractor_name == "allergy":
        results = allergy.extract(text, lang)
    elif extractor_name == "entities":
        results = entities.extract(text, lang)
    else:  # pragma: no cover - defensive, all names above are exhaustive
        raise ValueError(f"unknown extractor {extractor_name}")
    return [to_dict(r) for r in results]


def _all_fixture_files() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.jsonl"))


@pytest.mark.parametrize("fixture_path", _all_fixture_files(), ids=lambda p: p.stem)
def test_extractor_matches_fixture_grid(fixture_path: Path) -> None:
    extractor_name = fixture_path.stem
    rows = _load_rows(fixture_path)
    assert rows, f"{fixture_path} has no fixture rows"
    for i, row in enumerate(rows):
        actual = _run_one(extractor_name, row)
        assert actual == row["expect"], (
            f"{extractor_name} fixture row {i} ({row['text']!r}, {row['lang']}): "
            f"expected {row['expect']}, got {actual}"
        )


def test_extractor_conformance_is_1_00() -> None:
    """Computes and prints extractor_conformance across every fixture file, per EV-00."""
    total = 0
    passed = 0
    failures: list[str] = []
    for fixture_path in _all_fixture_files():
        extractor_name = fixture_path.stem
        for i, row in enumerate(_load_rows(fixture_path)):
            total += 1
            actual = _run_one(extractor_name, row)
            if actual == row["expect"]:
                passed += 1
            else:
                failures.append(
                    f"{extractor_name}#{i}: {row['text']!r} -> {actual} != {row['expect']}"
                )

    extractor_conformance = passed / total if total else 0.0
    print(f"extractor_conformance = {extractor_conformance:.2f} ({passed}/{total})")
    if failures:
        print("Failures:\n" + "\n".join(failures))
    assert extractor_conformance == 1.00, (
        f"extractor_conformance={extractor_conformance}, expected 1.00"
    )
