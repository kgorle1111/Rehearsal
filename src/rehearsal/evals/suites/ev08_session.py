"""EV-08 — end-to-end session completion and trainer-override rate.
misc/docs/08-evals.md §4.9.

BLOCKED-ON-HARDWARE: `session_completion_rate` and `turn_capture_loss_rate`
are computed over `data/fixtures/sessions/*.json` (replayable session
transcripts) plus real local session logs. Neither exists yet — there is no
real audio I/O, VAD, TTS, or live model host to produce a real session, and
no replay fixture has been authored (see NOT-BUILT-YET.md P2/P3).
`trainer_override_rate` additionally needs a human trainer's review diffs
against grader output, which is BLOCKED-ON-HUMAN on top of that.
"""

from __future__ import annotations

from pathlib import Path

from rehearsal.evals.result import EvalConfig, EvalResult, GateOutcome

SESSION_FIXTURES_DIR = Path("data/fixtures/sessions")


def run(cfg: EvalConfig) -> EvalResult:
    fixtures = sorted(SESSION_FIXTURES_DIR.glob("*.json")) if SESSION_FIXTURES_DIR.exists() else []
    return EvalResult(
        eval_id="EV-08",
        split=cfg.split,
        n=0,
        metrics={},
        intervals={},
        gate=GateOutcome.SKIPPED,
        gate_detail="no session fixtures or real session logs exist",
        artifacts=[],
        notes=(
            f"BLOCKED-ON-HARDWARE: data/fixtures/sessions/*.json has {len(fixtures)} files. "
            "session_completion_rate and turn_capture_loss_rate need real or replayable "
            "sessions, which need real audio I/O / VAD / TTS / a live model host — none "
            "exist yet (NOT-BUILT-YET.md P2/P3). trainer_override_rate is additionally "
            "BLOCKED-ON-HUMAN: it needs a human trainer's review diff against grader output."
        ),
    )
