"""EV-00 — deterministic extractor conformance. misc/docs/08-evals.md §4.1.

Wraps the same fixture-grid comparison WS1's own test
(tests/scoring/test_extractor_conformance.py) proves, as an EvalResult.
Does not duplicate that test file's assertions — reuses the extractor
modules directly, exactly as production's `run_extractors` does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

from rehearsal.evals.result import EvalConfig, EvalResult, GateOutcome
from rehearsal.scoring.extractors import allergy, dosage, entities, frequency, laterality, numbers
from rehearsal.scoring.extractors import negation as negation_mod

FIXTURES_DIR = Path("data/fixtures/extractors")

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
    rows: list[dict[str, Any]] = []
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
        results = negation_mod.check_targets(text, lang, tuple(row["targets"]))
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
    else:  # pragma: no cover - defensive, all fixture files above are exhaustive
        raise ValueError(f"unknown extractor {extractor_name}")
    return [to_dict(r) for r in results]


def run(cfg: EvalConfig) -> EvalResult:
    total = 0
    passed = 0
    failures: list[str] = []
    for fixture_path in sorted(FIXTURES_DIR.glob("*.jsonl")):
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

    conformance = passed / total if total else 0.0
    gate = GateOutcome.PASS if conformance == 1.00 else GateOutcome.FAIL
    notes = "clean" if not failures else "failures:\n" + "\n".join(failures)
    return EvalResult(
        eval_id="EV-00",
        split=cfg.split,
        n=total,
        metrics={"extractor_conformance": conformance},
        intervals={},
        gate=gate,
        gate_detail=f"extractor_conformance {conformance:.2f} ({passed}/{total}) == 1.00 required",
        artifacts=[],
        notes=notes,
    )
