from rehearsal.orchestrator.eventlog import GENESIS_HASH, EventLog


def test_first_event_chains_from_genesis() -> None:
    log = EventLog()
    e = log.append("s1", "session.created", {"trainee_id": "t1"})
    assert e.prev_hash == GENESIS_HASH
    assert e.seq == 1


def test_chain_links_within_a_session() -> None:
    log = EventLog()
    e1 = log.append("s1", "session.created", {})
    e2 = log.append("s1", "scenario.bound", {"node_id": "n0"})
    assert e2.prev_hash == e1.hash


def test_sessions_have_independent_chains() -> None:
    log = EventLog()
    log.append("s1", "session.created", {})
    e = log.append("s2", "session.created", {})
    assert e.prev_hash == GENESIS_HASH  # s2's chain starts fresh, unaffected by s1


def test_events_for_filters_by_session() -> None:
    log = EventLog()
    log.append("s1", "session.created", {})
    log.append("s2", "session.created", {})
    log.append("s1", "scenario.bound", {})
    assert [e.kind for e in log.events_for("s1")] == ["session.created", "scenario.bound"]


def test_verify_passes_on_untouched_log() -> None:
    log = EventLog()
    log.append("s1", "session.created", {})
    log.append("s1", "scenario.bound", {"node_id": "n0"})
    assert log.verify("s1") is True


def test_verify_detects_tampering() -> None:
    log = EventLog()
    log.append("s1", "session.created", {})
    log.append("s1", "scenario.bound", {"node_id": "n0"})
    # Simulate a silently edited record — mutate the stored event's payload
    # in place via object.__setattr__ since Event is frozen.
    tampered = log.events_for("s1")[1]
    object.__setattr__(tampered, "payload", {"node_id": "TAMPERED"})
    assert log.verify("s1") is False


def test_canonical_payload_is_order_independent() -> None:
    log = EventLog()
    e1 = log.append("s1", "k", {"a": 1, "b": 2})
    log2 = EventLog()
    e2 = log2.append("s1", "k", {"b": 2, "a": 1})
    assert e1.hash == e2.hash


if __name__ == "__main__":
    test_first_event_chains_from_genesis()
    test_chain_links_within_a_session()
    test_sessions_have_independent_chains()
    test_events_for_filters_by_session()
    test_verify_passes_on_untouched_log()
    test_verify_detects_tampering()
    test_canonical_payload_is_order_independent()
    print("eventlog: all checks passed")
