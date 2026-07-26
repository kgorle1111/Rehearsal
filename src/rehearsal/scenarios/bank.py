"""The scenario bank loader — the human-approval gate lives here.

CRITICAL CONSTRAINT (BUILD.md, this workstream's brief): a scenario whose
``review.status`` is not exactly ``"approved"`` must never be loadable by
the runtime. ``ScenarioBank.get()`` raises ``ScenarioNotApproved`` for any
other status. There is no override flag, no env var, no ``--force`` —
adding one defeats the point (misc/docs/07-data-and-scenarios.md §10.3).

Every scenario file also carries a ``provenance`` block (author, honesty
about review state). ``contracts.ScenarioRecord`` has no field for it — it
is a frozen contract this workstream does not extend — so provenance is
tracked bank-side, keyed by scenario_id, rather than smuggled into a
contract field that other workstreams read for something else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rehearsal.contracts import ScenarioRecord, ScenarioReview, TermManifestEntry
from rehearsal.scenarios.graph import clinical_state_from_dict, clinical_state_to_dict


class ScenarioNotApproved(Exception):
    """Raised by ScenarioBank.get() when review.status != 'approved'.

    No bypass mechanism exists anywhere in this module by design.
    """

    def __init__(self, scenario_id: str, status: str) -> None:
        self.scenario_id = scenario_id
        self.status = status
        super().__init__(
            f"scenario {scenario_id!r} is not approved (review.status={status!r}); "
            "a human must approve it before it can be loaded"
        )


@dataclass(frozen=True, slots=True)
class ScenarioProvenance:
    """Bank-local metadata, not part of the frozen contract. Honest record
    of who/what authored a scenario's clinical content."""

    author: str
    limitations: tuple[str, ...] = ()


def scenario_to_dict(record: ScenarioRecord) -> dict[str, Any]:
    """Convert a ``ScenarioRecord`` to a plain JSON-able dict."""
    return {
        "scenario_id": record.scenario_id,
        "schema_version": record.schema_version,
        "clinical_state": clinical_state_to_dict(record.clinical_state),
        "difficulty": record.difficulty,
        "term_manifest": [
            {
                "term_id": t.term_id,
                "kind": t.kind,
                "en": t.en,
                "es": t.es,
                "critical": t.critical,
                "acceptable_renderings": list(t.acceptable_renderings),
            }
            for t in record.term_manifest
        ],
        "review": {"status": record.review.status, "reviewer": record.review.reviewer},
    }


def scenario_from_dict(data: dict[str, Any]) -> ScenarioRecord:
    """Inverse of ``scenario_to_dict``. Raises KeyError on missing fields."""
    term_manifest = tuple(
        TermManifestEntry(
            term_id=t["term_id"],
            kind=t["kind"],
            en=t["en"],
            es=t["es"],
            critical=t["critical"],
            acceptable_renderings=tuple(t.get("acceptable_renderings", ())),
        )
        for t in data["term_manifest"]
    )
    review_data = data["review"]
    return ScenarioRecord(
        scenario_id=data["scenario_id"],
        schema_version=data["schema_version"],
        clinical_state=clinical_state_from_dict(data["clinical_state"]),
        difficulty=data["difficulty"],
        term_manifest=term_manifest,
        review=ScenarioReview(status=review_data["status"], reviewer=review_data.get("reviewer")),
    )


def _provenance_from_dict(data: dict[str, Any]) -> ScenarioProvenance:
    prov = data.get("provenance", {})
    return ScenarioProvenance(
        author=prov.get("author", "unknown"),
        limitations=tuple(prov.get("limitations", ())),
    )


def load_scenario_file(path: Path) -> tuple[ScenarioRecord, ScenarioProvenance]:
    """Load and parse one scenario JSON file. Does not check approval —
    that gate lives in ``ScenarioBank.get()`` so every read of a scenario
    (approved or not) goes through the same choke point."""
    data = json.loads(path.read_text())
    return scenario_from_dict(data), _provenance_from_dict(data)


class ScenarioBank:
    """Loads every scenario file in a directory; gates unapproved ones."""

    def __init__(self, directory: Path) -> None:
        self._records: dict[str, ScenarioRecord] = {}
        self._provenance: dict[str, ScenarioProvenance] = {}
        for path in sorted(directory.glob("*.json")):
            record, provenance = load_scenario_file(path)
            self._records[record.scenario_id] = record
            self._provenance[record.scenario_id] = provenance

    def get(self, scenario_id: str) -> ScenarioRecord:
        """Return the scenario, or raise ScenarioNotApproved if it has not
        been approved by a human reviewer. No override exists."""
        record = self._records[scenario_id]
        if record.review.status != "approved":
            raise ScenarioNotApproved(scenario_id, record.review.status)
        return record

    def get_provenance(self, scenario_id: str) -> ScenarioProvenance:
        return self._provenance[scenario_id]

    def load_all(self) -> tuple[ScenarioRecord, ...]:
        """Return every *approved* scenario. Unapproved scenarios are
        silently excluded here — the same rule ``get()`` enforces, applied
        to the bulk path so there is one gate, not two."""
        return tuple(r for r in self._records.values() if r.review.status == "approved")

    def list_ids(self) -> tuple[str, ...]:
        """All scenario ids in the bank, approved or not — for tooling
        (e.g. a review UI) that needs to see pending scenarios too."""
        return tuple(self._records.keys())
