"""Shared fixtures for the WS-API contract tests.

Every test gets its own `create_app()` (own db/blob/scenario dirs) per
the factory's own docstring intent — no `~/.rehearsal/` sharing, no
cross-test bleed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rehearsal.api.app import create_app

APPROVED_SCENARIO_ID = "sc_test_0001_approved"


def approved_scenario_dict(scenario_id: str = APPROVED_SCENARIO_ID) -> dict[str, Any]:
    """A minimal, schema-valid, human-*approved* scenario — deliberately not
    one of the real `data/scenarios/*.json` files (all 5 are `pending` by
    design, see NOT-BUILT-YET.md). Marking a real seed scenario "approved"
    is a human's call, not a test fixture's."""
    return {
        "scenario_id": scenario_id,
        "schema_version": "1.0.0",
        "clinical_state": {
            "condition": "type 2 diabetes mellitus",
            "medications": [
                {
                    "name": "metformin",
                    "dose": "500",
                    "unit": "mg",
                    "route": "oral",
                    "frequency_per_day": 2,
                    "duration": "4 years",
                }
            ],
            "symptom_timeline": [{"offset": "3 weeks ago", "symptom": "fatigue"}],
            "allergies": [{"substance": "penicillin"}],
            "emotional_state": "worried",
            "health_literacy": "low",
            "language_variety": "es-MX-rural-central",
            "onset": "3 weeks ago, gradual",
        },
        "difficulty": {"band": "intermediate"},
        "term_manifest": [
            {
                "term_id": "med_metformin_dose",
                "kind": "dosage",
                "en": "500 mg",
                "es": "500 mg",
                "critical": True,
                "acceptable_renderings": ["500 mg"],
            }
        ],
        "review": {"status": "approved", "reviewer": "test-fixture"},
        "provenance": {"author": "test-fixture", "limitations": []},
    }


@pytest.fixture
def scenario_dir(tmp_path: Path) -> Path:
    d = tmp_path / "scenarios"
    d.mkdir()
    (d / f"{APPROVED_SCENARIO_ID}.json").write_text(json.dumps(approved_scenario_dict()))
    return d


@pytest.fixture
def app(tmp_path: Path, scenario_dir: Path) -> FastAPI:
    # `create_app()` calls `store.db.connect()` directly (app.py: `conn =
    # connect(db_path)`) — the identical function `tests/store/test_db.py`
    # already covers for "migrations run clean" (fresh connect, idempotent
    # re-connect, tampered-migration failure). No separate migration path
    # exists in the API layer to duplicate that coverage for.
    return create_app(
        db_path=tmp_path / "db" / "rehearsal.db",
        blob_root=tmp_path / "blobs",
        scenario_dir=scenario_dir,
    )


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
