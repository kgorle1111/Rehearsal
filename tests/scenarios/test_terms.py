from __future__ import annotations

from rehearsal.contracts import TermManifestEntry
from rehearsal.scenarios.terms import build_term_manifest_entry, expand_renderings


def test_output_conforms_to_term_manifest_entry_contract() -> None:
    """Contract test: the generator's output must be exactly the shape the
    scoring engine's extractors consume (contracts.TermManifestEntry)."""
    entry = build_term_manifest_entry(
        term_id="med_metformin_dose", kind="dosage", en="500 mg", es="500 mg", critical=True
    )
    assert isinstance(entry, TermManifestEntry)
    assert entry.term_id == "med_metformin_dose"
    assert entry.kind == "dosage"
    assert entry.en == "500 mg"
    assert entry.es == "500 mg"
    assert entry.critical is True
    assert isinstance(entry.acceptable_renderings, tuple)
    assert all(isinstance(r, str) for r in entry.acceptable_renderings)


def test_original_forms_always_present() -> None:
    renderings = expand_renderings("penicillin", "penicilina")
    assert "penicillin" in renderings
    assert "penicilina" in renderings


def test_numeral_expansion_en_and_es() -> None:
    renderings = expand_renderings("4 days ago", "hace 4 dias")
    assert "four days ago" in renderings
    assert "hace cuatro dias" in renderings


def test_unit_expansion_mg() -> None:
    renderings = expand_renderings("500 mg", "500 mg")
    assert "500 milligrams" in renderings
    assert "500 miligramos" in renderings


def test_unit_expansion_singular_for_one() -> None:
    renderings = expand_renderings("1 mg", "1 mg")
    assert "1 milligram" in renderings
    assert "1 miligramo" in renderings


def test_pluralization_single_word() -> None:
    renderings = expand_renderings("penicillin", "penicilina")
    assert "penicillins" in renderings
    assert "penicilinas" in renderings


def test_pluralization_skipped_for_multi_word() -> None:
    # Naive pluralization only applies to single-word terms; a phrase like
    # "chest pain" is not touched by rule 4.
    renderings = expand_renderings("chest pain", "dolor de pecho")
    assert "chest pains" not in renderings


def test_no_numeral_is_a_no_op() -> None:
    renderings = expand_renderings("worried", "preocupada")
    assert renderings == ("worried", "preocupada", "worrieds", "preocupadas")


def test_deterministic_and_deduplicated() -> None:
    first = expand_renderings("2 mg", "2 mg")
    second = expand_renderings("2 mg", "2 mg")
    assert first == second
    assert len(first) == len(set(first))
