#!/usr/bin/env python3
"""
label_quiz.py — interactive, one-at-a-time calibration labelling for Rehearsal.

WHY THIS EXISTS
    Labelling the 40-item calibration set (misc/SETUP.md section 6) by hand in
    a markdown table is slow and error-prone. This script presents one item at
    a time, asks structured multiple-choice questions, and writes a labels
    file you can feed into `make split-calibration` later.

THE LANGUAGE SPLIT (read this before using the tool)
    A calibration item has a DIRECTION:
      es_to_en  — the patient speaks Spanish; the trainee renders to English.
                  The rendering you judge is in ENGLISH. A monolingual English
                  speaker can label these directly, by comparing the trainee's
                  English rendering against `fact_en` — the English clinical
                  fact the scenario was built from, which exists independently
                  of any rendering.
      en_to_es  — the clinician speaks English; the trainee renders to Spanish.
                  The rendering you'd judge is in SPANISH. There is no honest
                  shortcut for a monolingual reviewer here: any gloss check
                  would just be confirming content someone already wrote, not
                  an independent judgement. This tool refuses to quiz you on
                  these — it queues them to `needs-bilingual.jsonl` instead.

    Recruit one bilingual person to label the en_to_es queue. This also
    satisfies SETUP.md's inter-rater-reliability recommendation, so it is not
    wasted effort — it is the second labeller the protocol already wants.

USAGE
    python3 label_quiz.py --items items.jsonl --out labels.jsonl

    Resumable: items already present in --out are skipped on the next run.
    Ctrl-C at any time is safe — only fully-answered items are written.

ITEM FILE FORMAT (one JSON object per line)
    {"id": "c07", "direction": "es_to_en",
     "fact_en": "Take one tablet twice a day with food.",
     "rendering_text": "Take one tablet once a day with food."}

    For en_to_es items, `rendering_text` may be omitted here — this tool
    never displays or asks about it; the bilingual reviewer handles those
    directly from the item file, by whatever method they prefer.

No third-party dependencies. Python 3.9+.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

TAXONOMY = [
    ("omission", "Content in the source is missing from the rendering"),
    ("addition", "Rendering contains content not in the source"),
    ("substitution", "Content replaced with different content"),
    ("distortion", "Meaning materially altered, including negation flips"),
    ("editorialization", "Interpreter's own opinion/explanation inserted"),
    ("role_exchange", "Interpreter speaks on their own behalf instead of interpreting"),
    ("register_shift", "Formality/style/tone materially changed"),
    ("false_fluency", "Invented or borrowed term instead of interpreting the concept"),
    ("first_person_violation", "Reported speech (\"he says that...\") instead of first person"),
]


def ask(prompt: str, valid: Optional[set[str]] = None) -> str:
    while True:
        ans = input(prompt).strip()
        if valid is None or ans.lower() in valid:
            return ans
        print(f"  (please answer one of: {', '.join(sorted(valid))})")


def ask_yn(prompt: str) -> bool:
    return ask(prompt + " [y/n]: ", {"y", "n"}).lower() == "y"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_jsonl(path: Path, obj: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def label_one_item(item: dict) -> dict:
    """Run the interactive quiz for one es_to_en item. Returns the label record."""
    print("\n" + "=" * 72)
    print(f"ITEM {item['id']}  ·  direction: patient (Spanish) → you interpret to English")
    print("-" * 72)
    print("What the patient meant (independent English ground truth):")
    print(f"    \"{item['fact_en']}\"")
    print()
    print("The trainee's English rendering:")
    print(f"    \"{item['rendering_text']}\"")
    print("=" * 72)

    findings = []
    is_clean = ask_yn("\nDoes the rendering fully and accurately convey the meaning above?")

    if not is_clean:
        while True:
            print("\nWhat kind of error is this? (you can add more than one)")
            for i, (name, desc) in enumerate(TAXONOMY, 1):
                print(f"  {i}. {name:<24} — {desc}")
            choice = ask(
                f"Enter a number (1-{len(TAXONOMY)}): ",
                {str(i) for i in range(1, len(TAXONOMY) + 1)},
            )
            err_type, _ = TAXONOMY[int(choice) - 1]

            print(
                "\nSeverity — ask yourself: could a clinician or patient reasonably act "
                "differently because of this? (a dosage, frequency, negation, allergy, "
                "laterality or symptom-onset error is almost always CRITICAL)"
            )
            severity = ask("Severity — (c)ritical or (n)on-critical? ", {"c", "n"})
            severity = "critical" if severity == "c" else "non_critical"

            note = input("Optional one-line note (press Enter to skip): ").strip()

            findings.append({"type": err_type, "severity": severity, "note": note})

            if not ask_yn("Any OTHER error in this same item?"):
                break

    print("\nHow confident are you in this label?")
    conf = ask("  (s)ure or (u)nsure: ", {"s", "u"})
    confidence = "sure" if conf == "s" else "unsure"

    return {
        "id": item["id"],
        "direction": item["direction"],
        "clean": is_clean,
        "findings": findings,
        "confidence": confidence,
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--items", required=True, type=Path, help="Input JSONL of calibration items")
    p.add_argument("--out", required=True, type=Path, help="Output JSONL of your labels (appended, resumable)")
    p.add_argument(
        "--needs-bilingual-out",
        type=Path,
        default=None,
        help="Where to queue en_to_es items (default: <items-dir>/needs-bilingual.jsonl)",
    )
    args = p.parse_args()

    needs_bilingual_path = args.needs_bilingual_out or (args.items.parent / "needs-bilingual.jsonl")

    all_items = load_jsonl(args.items)
    if not all_items:
        print(f"No items found in {args.items}. Nothing to do.")
        return 1

    already_labeled = {r["id"] for r in load_jsonl(args.out)}
    already_queued = {r["id"] for r in load_jsonl(needs_bilingual_path)}

    es_to_en = [it for it in all_items if it.get("direction") == "es_to_en" and it["id"] not in already_labeled]
    en_to_es = [it for it in all_items if it.get("direction") == "en_to_es" and it["id"] not in already_queued]

    # Queue every en_to_es item immediately, without showing its content to you.
    for it in en_to_es:
        append_jsonl(needs_bilingual_path, {"id": it["id"], "direction": "en_to_es"})
    if en_to_es:
        print(
            f"Queued {len(en_to_es)} en_to_es item(s) to {needs_bilingual_path} "
            "— these need a bilingual reviewer, not you. Not shown here."
        )

    if not es_to_en:
        print("No es_to_en items left for you to label. Recruit a bilingual reviewer for the rest.")
        return 0

    print(f"\n{len(es_to_en)} item(s) ready for you (es_to_en direction). Ctrl-C anytime to stop safely.\n")

    done = 0
    try:
        for it in es_to_en:
            label = label_one_item(it)
            append_jsonl(args.out, label)
            done += 1
            print(f"\nSaved. ({done}/{len(es_to_en)} this session)")
    except KeyboardInterrupt:
        print(f"\n\nStopped early. {done} label(s) saved this session — re-run to resume where you left off.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
