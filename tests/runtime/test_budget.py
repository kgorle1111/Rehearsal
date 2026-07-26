from rehearsal.runtime.budget import BudgetGuard, DegradeLevel, TurnBudget, UnknownBudgetStage


def test_defaults_match_spec() -> None:
    b = TurnBudget()
    assert b.source_generation_ms == 900
    assert b.tts_first_audio_ms == 400
    assert b.barge_in_stop_ms == 120
    assert b.capture_max_ms == 45_000
    assert b.grader_wall_ms == 3_500
    assert b.persist_turn_ms == 50


def test_within_budget_no_degrade() -> None:
    guard = BudgetGuard(TurnBudget())
    within, degrade = guard.check("grader_wall_ms", 1000)
    assert within is True
    assert degrade is None


def test_single_overshoot_does_not_shed() -> None:
    guard = BudgetGuard(TurnBudget())
    within, degrade = guard.check("grader_wall_ms", 4000)
    assert within is False
    assert degrade is None  # not sustained yet


def test_sustained_overshoot_sheds_l2() -> None:
    guard = BudgetGuard(TurnBudget())
    guard.check("grader_wall_ms", 4000)
    within, degrade = guard.check("grader_wall_ms", 4200)
    assert within is False
    assert degrade is DegradeLevel.L2


def test_recovery_resets_overshoot_counter() -> None:
    guard = BudgetGuard(TurnBudget())
    guard.check("grader_wall_ms", 4000)
    guard.check("grader_wall_ms", 1000)  # back within budget
    within, degrade = guard.check("grader_wall_ms", 4000)
    assert degrade is None  # counter reset, not sustained


def test_non_grader_stage_never_signals_degrade() -> None:
    guard = BudgetGuard(TurnBudget())
    for _ in range(5):
        within, degrade = guard.check("capture_max_ms", 50_000)
        assert within is False
        assert degrade is None


def test_unknown_stage_raises() -> None:
    guard = BudgetGuard(TurnBudget())
    try:
        guard.check("not_a_stage", 10)
    except UnknownBudgetStage:
        pass
    else:
        raise AssertionError("expected UnknownBudgetStage")


if __name__ == "__main__":
    test_defaults_match_spec()
    test_within_budget_no_degrade()
    test_single_overshoot_does_not_shed()
    test_sustained_overshoot_sheds_l2()
    test_recovery_resets_overshoot_counter()
    test_non_grader_stage_never_signals_degrade()
    test_unknown_stage_raises()
    print("budget: all checks passed")
