"""Isolation boundary tests. misc/docs/04-ai-engineering.md §5.

Covers: allowlist enforcement, the taxonomy-vocabulary canary, allowlist
totality over roles, and the leakage A/B harness (mechanism-level only — no
live model host exists yet, so no behavioral delta is claimed).
"""

from __future__ import annotations

import itertools

import pytest

from rehearsal.agents.isolation import (
    BANNED_SUBSTRINGS,
    FIELD_ALLOWLIST,
    IsolationViolation,
    Role,
    assemble,
    assemble_leaked,
    run_leakage_ab,
)

CLINICIAN_FIELDS: dict[str, object] = {
    "role_card": "Dr. Alvarez, ER attending, 12 years experience.",
    "node": "n_04_ask_allergies",
    "encounter_summary": "Patient presents with chest pain, onset 2 hours ago.",
    "recent_turns": ("Do you have any allergies?",),
    "difficulty": 3,
    "style_directives": "brisk, clinical register",
    "audio_ref": "blob:abc123",
}

PATIENT_FIELDS: dict[str, object] = {
    "role_card": "Maria, 54, construction worker, health literacy: low.",
    "node": "n_04_ask_allergies",
    "encounter_summary": "Anxious about missing work; pain started after lifting.",
    "recent_turns": ("¿Tiene alguna alergia?",),
    "difficulty": 3,
    "style_directives": "anxious, informal register",
    "audio_ref": "blob:def456",
}

COACH_FIELDS: dict[str, object] = {
    "verdict_summary": "Missed two dosage confirmations this session.",
    "weak_categories": ("dosage", "frequency"),
    "turns_remaining": 4,
    "tone": "encouraging",
}


# --- allowlist enforcement -------------------------------------------------


def test_allowlist_rejects_disallowed_field() -> None:
    with pytest.raises(IsolationViolation, match="rubric_text"):
        assemble("patient", {**PATIENT_FIELDS, "rubric_text": "critical error taxonomy"})


def test_allowlist_rejects_disallowed_field_clinician() -> None:
    with pytest.raises(IsolationViolation, match="weak_categories"):
        assemble("clinician", {**CLINICIAN_FIELDS, "weak_categories": ("dosage",)})


def test_allowlist_accepts_allowed_fields() -> None:
    ctx = assemble("patient", PATIENT_FIELDS)
    assert ctx.role == "patient"
    assert len(ctx.context_sha) == 64


def test_allowlist_is_total_over_roles() -> None:
    """Every Role has an entry — adding a role without deciding its allowlist
    is a build-time failure, not a runtime surprise."""
    role_values: tuple[Role, ...] = ("clinician", "patient", "coach")
    for role in role_values:
        assert role in FIELD_ALLOWLIST, f"role {role!r} has no allowlist entry"


# --- vocabulary canary ------------------------------------------------------


@pytest.mark.parametrize("banned_term", sorted(BANNED_SUBSTRINGS))
def test_canary_catches_each_banned_term(banned_term: str) -> None:
    fields = {**PATIENT_FIELDS, "style_directives": f"remember: {banned_term}"}
    with pytest.raises(IsolationViolation, match="rubric vocabulary"):
        assemble("patient", fields)


def test_live_context_has_no_taxonomy_vocabulary() -> None:
    """Assemble many plausible contexts for clinician and patient; none
    contains a banned substring."""
    style_options = ("brisk, clinical register", "warm, patient", "terse", "formal Spanish")
    node_options = (
        "n_01_greeting", "n_02_chief_complaint", "n_03_history",
        "n_04_ask_allergies", "n_05_medication_review", "n_06_disposition",
    )
    difficulty_options = (1, 2, 3, 4, 5)

    for role, base in (("clinician", CLINICIAN_FIELDS), ("patient", PATIENT_FIELDS)):
        for node, style, difficulty in itertools.product(
            node_options, style_options, difficulty_options
        ):
            fields = {**base, "node": node, "style_directives": style, "difficulty": difficulty}
            ctx = assemble(role, fields)  # type: ignore[arg-type]  # role: str, narrowed by the tuple literals above
            lowered = ctx.text.lower()
            hits = [t for t in BANNED_SUBSTRINGS if t in lowered]
            assert not hits, f"role={role} node={node} leaked: {hits}"


def test_coach_context_unaffected_by_canary() -> None:
    """Coach isn't a live counterpart agent — it may legitimately discuss
    weak categories. Only clinician/patient are scanned."""
    ctx = assemble("coach", COACH_FIELDS)
    assert "dosage" in ctx.text.lower()


# --- leakage A/B harness -----------------------------------------------------


def test_leaked_arm_widens_allowlist_by_exactly_one_field() -> None:
    leaked = assemble_leaked("patient", {**PATIENT_FIELDS, "rubric_text": "some paraphrased note"})
    assert leaked.role == "patient"


def test_leaked_arm_rejects_further_disallowed_fields() -> None:
    with pytest.raises(IsolationViolation):
        assemble_leaked(
            "patient",
            {**PATIENT_FIELDS, "rubric_text": "note", "weak_categories": ("dosage",)},
        )


def test_assemble_leaked_only_for_counterpart_roles() -> None:
    with pytest.raises(IsolationViolation):
        assemble_leaked("coach", COACH_FIELDS)


def test_leakage_ab_reports_sha_delta_when_rubric_text_is_benign() -> None:
    """Paraphrased rubric text (no literal canary words) — the allowlist is
    the only thing standing between this and a live model; the canary can't
    catch it, matching §5.3's stated limitation."""
    result = run_leakage_ab(
        "patient", PATIENT_FIELDS, rubric_text="the trainee tends to skip confirming numbers"
    )
    assert not result.canary_blocked_leaked_arm
    assert result.leaked is not None
    assert result.context_sha_differs is True
    assert result.clean.context_sha != result.leaked.context_sha
    assert result.behavioral_delta is None


def test_leakage_ab_reports_canary_block_when_rubric_text_is_crude() -> None:
    result = run_leakage_ab("patient", PATIENT_FIELDS, rubric_text="this is a critical error")
    assert result.canary_blocked_leaked_arm
    assert result.leaked is None
    assert result.context_sha_differs is None


def test_leakage_ab_report_is_honest_about_behavioral_delta() -> None:
    result = run_leakage_ab("clinician", CLINICIAN_FIELDS, rubric_text="benign paraphrase")
    text = result.report()
    assert "behavioral/session-level delta: —" in text
    assert "not yet available" in text
