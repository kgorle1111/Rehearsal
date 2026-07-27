"""`rehearsal-evals` entry point. misc/docs/08-evals.md §2.3.

Minimal: `run --eval <id>` executes one suite and records it in the
registry; `report --run <run_id>` re-renders a recorded run without
re-executing it. Split/seed/unseal-reason plumbing beyond that is left to
grow when a suite actually needs it (dry_run and the fuller EvalConfig
surface already exist in result.py for that day).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

from rehearsal.evals import registry, seal
from rehearsal.evals.result import EvalConfig, EvalResult
from rehearsal.evals.suites import (
    ev00_extractors,
    ev01_calibration,
    ev02_critical_recall,
    ev03_human_ceiling,
    ev05_leakage,
    ev07_latency,
    ev08_session,
)

SUITES: dict[str, Callable[[EvalConfig], EvalResult]] = {
    "EV-00": ev00_extractors.run,
    "EV-01": ev01_calibration.run,
    "EV-02": ev02_critical_recall.run,
    "EV-03": ev03_human_ceiling.run,
    "EV-05": ev05_leakage.run,
    "EV-07": ev07_latency.run,
    "EV-08": ev08_session.run,
}


def _cmd_run(args: argparse.Namespace) -> int:
    suite = SUITES.get(args.eval)
    if suite is None:
        print(f"unknown eval id {args.eval!r}; known: {sorted(SUITES)}", file=sys.stderr)
        return 2

    if args.split == "test":
        if not args.unseal_reason:
            print("split=test requires --unseal-reason", file=sys.stderr)
            return 2
        seal.unseal(args.unseal_reason)

    cfg = EvalConfig(split=args.split, seed=args.seed)
    result = suite(cfg)
    print(f"{result.eval_id} [{result.gate.value}] n={result.n} {result.gate_detail}")
    if result.metrics:
        print(f"  metrics: {result.metrics}")
    if result.notes:
        print(f"  notes: {result.notes}")

    try:
        run_id = registry.record_run(result)
        print(f"  recorded as {run_id}")
    except registry.RegistryError as e:
        print(f"  NOT recorded: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    row = registry.read_run(args.run)
    print(json.dumps(row, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rehearsal-evals")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run one eval suite and record it.")
    p_run.add_argument("--eval", required=True, help="Eval id, e.g. EV-00")
    p_run.add_argument(
        "--split", default="fixture", choices=["dev", "test", "fixture", "live", "replay"]
    )
    p_run.add_argument("--seed", type=int, default=0)
    p_run.add_argument("--unseal-reason", default=None, help="Required when --split test")
    p_run.set_defaults(func=_cmd_run)

    p_report = sub.add_parser("report", help="Re-render a recorded run.")
    p_report.add_argument("--run", required=True, help="run_id")
    p_report.set_defaults(func=_cmd_report)

    ns = parser.parse_args(argv)
    result: int = ns.func(ns)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
