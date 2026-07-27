"""The rehearsal CLI.

Commands:
    rehearsal review [--scenarios DIR]        human scenario approval (the gate)
    rehearsal demo   [--scenario ID] [...]    text-mode end-to-end session

Demo scope (text mode): the patient agent speaks Spanish via a local Gemma
(Ollama), you type your English rendering, the neuro-symbolic scorer
(deterministic extractors + one structured grader call) scores the turn, the
coach gives one hint. Voice, the API server, and the frontend are deferred —
see ROADMAP.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from rehearsal.agents.coach import CoachAgent
from rehearsal.agents.model_client import ConversationNode
from rehearsal.agents.patient import PatientAgent
from rehearsal.contracts import Direction, ScoreRecord, Severity, SpeakerRole, TurnRecord

_SCENARIO_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def _load_raw(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def cmd_review(args: argparse.Namespace) -> int:
    """Show each pending scenario and let a human approve/reject it.

    This IS the approval gate's front door — the bank refuses unapproved
    scenarios and has no override, so the only way to run one is for a
    human to read it here and put their name on it.
    """
    directory: Path = args.scenarios
    pending = [
        p
        for p in sorted(directory.glob("*.json"))
        if _load_raw(p)["review"]["status"] != "approved"
    ]
    if not pending:
        print("No pending scenarios — everything is already reviewed.")
        return 0
    reviewer = input("Your name (recorded as reviewer): ").strip()
    if not reviewer:
        print("A reviewer name is required.")
        return 1
    for path in pending:
        data = _load_raw(path)
        print("\n" + "=" * 70)
        print(f"SCENARIO {data['scenario_id']}  (status: {data['review']['status']})")
        print("=" * 70)
        keys = ("clinical_state", "difficulty", "term_manifest")
        print(json.dumps({k: data[k] for k in keys}, indent=2))
        ans = input("\nApprove this scenario? Read it first. [y/n/skip]: ").strip().lower()
        if ans == "y":
            data["review"] = {"status": "approved", "reviewer": reviewer}
            path.write_text(json.dumps(data, indent=1) + "\n")
            print("approved.")
        elif ans == "n":
            data["review"] = {"status": "rejected", "reviewer": reviewer}
            path.write_text(json.dumps(data, indent=1) + "\n")
            print("rejected.")
        else:
            print("skipped.")
    return 0


def _print_findings(score: ScoreRecord) -> None:
    if not score.findings:
        print("  ✓ clean — no findings")
        return
    for f in score.findings:
        sev = "CRITICAL" if f.severity is Severity.CRITICAL else "non-critical"
        origin = f.extractor_name or f.provenance.value
        conf = f" (conf {f.confidence:.2f})" if f.confidence is not None else ""
        print(f"  ✗ [{sev}] {f.type.value} — {f.note}  ({origin}{conf})")


def cmd_demo(args: argparse.Namespace) -> int:
    # Imported here so `rehearsal review` works without Ollama running.
    from rehearsal.hosts.ollama import (
        OllamaGraderClient,
        OllamaLiveClient,
        OllamaUnavailable,
        check_facts_present,
    )
    from rehearsal.scenarios.bank import ScenarioBank, ScenarioNotApproved
    from rehearsal.scoring.engine import score_turn

    bank = ScenarioBank(args.scenarios)
    scenario_id = args.scenario or (bank.list_ids()[0] if bank.list_ids() else None)
    if scenario_id is None:
        print("No scenarios found.", file=sys.stderr)
        return 1
    try:
        scenario = bank.get(scenario_id)
    except ScenarioNotApproved as e:
        print(f"{e}\n\nRun `rehearsal review` first — a human must approve it.", file=sys.stderr)
        return 1

    live = OllamaLiveClient(model=args.model, host=args.host)
    grader = OllamaGraderClient(model=args.model, host=args.host)
    patient = PatientAgent(client=live)
    coach = CoachAgent()
    state = scenario.clinical_state

    # ponytail: fixed node plan — timeline, then meds, then allergies, one
    # fact-group per turn. Real graph traversal is WS7's deferred piece.
    fact_groups = [g for g in (state.symptom_timeline, state.medications, state.allergies) if g]
    session_id = f"demo-{uuid.uuid4().hex[:8]}"

    print(f"\nScenario: {scenario.scenario_id}  ·  session {session_id}")
    print("The patient speaks Spanish. Type your English interpretation after each turn.")
    print("(Blank line to skip a turn, Ctrl-C to quit.)\n")

    results: list[ScoreRecord] = []
    try:
        for i, group in enumerate(fact_groups, 1):
            node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=tuple(group))
            print(f"— turn {i}/{len(fact_groups)} · patient is speaking (Gemma, local) …")
            try:
                turn_out = patient.take_turn(state, node)
            except OllamaUnavailable as e:
                print(f"\n{e}", file=sys.stderr)
                return 1
            print(f'\n  PATIENT (es): "{turn_out.reply_text}"\n')
            missing = check_facts_present(node, turn_out.reply_text)
            if missing:
                print(
                    "  WARNING: this line may not be reliable scoring ground truth — "
                    "the model's utterance appears to be missing: "
                    + "; ".join(missing)
                    + "\n  (see NOT-BUILT-YET.md P-extra: a live model's output isn't "
                    "verified ground-truth-by-construction the way the scripted "
                    "client's is.)\n"
                )
            rendering = input("  Your English rendering > ").strip()
            if not rendering:
                print("  (skipped)\n")
                continue
            turn = TurnRecord(
                turn_id=f"{session_id}-t{i}",
                session_id=session_id,
                direction=Direction.ES_TO_EN,
                source_utterance=turn_out.reply_text,
                source_lang="es",
                rendering_transcript=rendering,
            )
            print("  scoring (extractors + grader) …")
            score = score_turn(
                turn,
                grader,
                speaker=SpeakerRole.PATIENT,
                grader_prompt_version=grader.prompt_version,
            )
            results.append(score)
            _print_findings(score)
            hint = coach.generate_hint(score.findings)
            if not hint.suppress:
                print(f"  coach: {hint.hint}")
            print()
    except (KeyboardInterrupt, EOFError):
        print("\n(session ended early)")

    total = sum(len(s.findings) for s in results)
    crit = sum(1 for s in results for f in s.findings if f.severity is Severity.CRITICAL)
    print("=" * 60)
    print(f"Session summary: {len(results)} turn(s) scored · {total} finding(s) · {crit} critical")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="rehearsal", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("review", help="human scenario approval gate")
    pr.add_argument("--scenarios", type=Path, default=_SCENARIO_DIR)
    pr.set_defaults(func=cmd_review)

    pd = sub.add_parser("demo", help="text-mode end-to-end session")
    pd.add_argument("--scenario", help="scenario id (default: first in bank)")
    pd.add_argument("--scenarios", type=Path, default=_SCENARIO_DIR)
    pd.add_argument("--model", default="gemma4:e4b-mlx")
    pd.add_argument("--host", default="http://localhost:11434")
    pd.set_defaults(func=cmd_demo)

    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
