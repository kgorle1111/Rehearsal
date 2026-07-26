import hashlib

from rehearsal.orchestrator.seeds import NAMESPACES, derive_seed


def test_deterministic_repeat() -> None:
    assert derive_seed(42, "graph_walk", 3) == derive_seed(42, "graph_walk", 3)


def test_sensitive_to_root_seed() -> None:
    assert derive_seed(1, "graph_walk", 0) != derive_seed(2, "graph_walk", 0)


def test_sensitive_to_namespace() -> None:
    assert derive_seed(1, "graph_walk", 0) != derive_seed(1, "clinician_sampling", 0)


def test_sensitive_to_turn_index() -> None:
    assert derive_seed(1, "graph_walk", 0) != derive_seed(1, "graph_walk", 1)


def test_matches_spec_formula_exactly() -> None:
    root_seed, namespace, turn_index = 12345, "patient_sampling", 7
    expected = int.from_bytes(
        hashlib.blake2b(f"{root_seed}:{namespace}:{turn_index}".encode(), digest_size=8).digest(),
        "big",
    )
    assert derive_seed(root_seed, namespace, turn_index) == expected


def test_namespaces_tuple_matches_spec() -> None:
    assert NAMESPACES == (
        "scenario_selection",
        "graph_walk",
        "clinician_sampling",
        "patient_sampling",
        "coach_sampling",
        "distractor_injection",
    )


if __name__ == "__main__":
    test_deterministic_repeat()
    test_sensitive_to_root_seed()
    test_sensitive_to_namespace()
    test_sensitive_to_turn_index()
    test_matches_spec_formula_exactly()
    test_namespaces_tuple_matches_spec()
    print("seeds: all checks passed")
