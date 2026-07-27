"""Static PHI-shape scanner over committed scenario/calibration content.

misc/docs/12-security-privacy.md §6.2 describes a layered "no real patient
data" defense: an ingest gate + a deterministic PHI-shaped-content scanner.
Neither exists yet (P5 security review, 2026-07-27) — the current 5 seed
scenarios and the calibration item bank were verified by hand to be
synthetic, but nothing would catch a future contributor pasting a real case
into a new file. This is the cheap substitute: a regex sweep for
SSN/MRN/phone/DOB-shaped strings over every committed scenario and
calibration file, run as a normal test so it's part of `pytest`/CI rather
than a one-off manual check.

This is NOT the full layered defense the doc describes (no ingest-time
gate, no UI affirmation step) — see NOT-BUILT-YET.md P-extra. It only
catches content already in the repo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS_DIR = _REPO_ROOT / "data" / "scenarios"
_CALIBRATION_ITEMS = _REPO_ROOT / "data" / "calibration" / "items.jsonl"

# Deliberately coarse — these are shape checks, not a full PHI classifier.
# A false positive here just means a human looks once; a false negative
# means real PHI ships silently, so the patterns favor over-catching.
_PHI_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "mrn_labelled": re.compile(r"\bMRN\s*[:#]?\s*\d{4,}\b", re.IGNORECASE),
    "phone": re.compile(r"\b\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
    "dob_labelled": re.compile(r"\b(DOB|date of birth)\s*[:#]?\s*\d", re.IGNORECASE),
    "npi_labelled": re.compile(r"\bNPI\s*[:#]?\s*\d{10}\b", re.IGNORECASE),
}


def _scan_text(text: str) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for name, pattern in _PHI_PATTERNS.items():
        found = pattern.findall(text)
        if found:
            hits[name] = found
    return hits


def _scenario_files() -> list[Path]:
    if not _SCENARIOS_DIR.is_dir():
        return []
    return sorted(_SCENARIOS_DIR.glob("*.json"))


def test_no_phi_shaped_content_in_scenarios() -> None:
    offenders = {}
    for path in _scenario_files():
        hits = _scan_text(path.read_text(encoding="utf-8"))
        if hits:
            offenders[str(path)] = hits
    assert not offenders, (
        f"PHI-shaped content found in scenario files: {offenders}. "
        f"Scenarios must be synthetic — misc/docs/12-security-privacy.md §6.2."
    )


def test_no_phi_shaped_content_in_calibration_items() -> None:
    if not _CALIBRATION_ITEMS.is_file():
        return  # nothing to scan yet
    offenders = {}
    for i, line in enumerate(_CALIBRATION_ITEMS.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        hits = _scan_text(json.dumps(row))
        if hits:
            offenders[f"line {i}"] = hits
    assert not offenders, (
        f"PHI-shaped content found in calibration items: {offenders}. "
        f"Calibration items must be synthetic — misc/docs/12-security-privacy.md §6.2."
    )
