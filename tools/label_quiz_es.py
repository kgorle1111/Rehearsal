#!/usr/bin/env python3
"""
label_quiz_es.py — interactive calibration labelling for the en_to_es direction.

This is the bilingual counterpart to label_quiz.py. Where that tool only
handles es_to_en items (rendering in English, safe for a monolingual reviewer),
this one handles en_to_es items: the clinician's ORIGINAL ENGLISH utterance
against the trainee's SPANISH rendering. It shows both languages directly —
appropriate here, because the person running this tool is assumed bilingual
and can make a genuine independent judgement, which is exactly what the
monolingual tool could not honestly claim to support (see tools/README.md).

USAGE
    python3 label_quiz_es.py --items items.jsonl --out labels_es.jsonl

    Reads the SAME master items file your English-speaking teammate used —
    this tool filters to direction == "en_to_es" itself. You do not need the
    needs-bilingual.jsonl queue file; that was only a heads-up for your
    teammate to know these items existed. Resumable, same as the English tool.

ITEM FILE FORMAT — the en_to_es fields this tool reads (one JSON object/line)
    {"id": "c12", "direction": "en_to_es",
     "source_text": "Take one tablet twice a day with food.",
     "rendering_text": "Tome una pastilla al día con comida."}

OUTPUT — identical schema to label_quiz.py's output, so both files merge
cleanly for the dev/test split in misc/SETUP.md section 6.6:
    {"id":..., "direction":..., "clean": bool, "findings": [...], "confidence":...}

No third-party dependencies. Python 3.9+.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
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
    """Run the interactive quiz for one en_to_es item."""
    print("\n" + "=" * 72)
    print(f"ITEM {item['id']}  ·  direction: clinician (English) → interpreted to Spanish")
    print("-" * 72)
    print("What the clinician actually said (English source):")
    print(f"    \"{item['source_text']}\"")
    print()
    print("The trainee's Spanish rendering:")
    print(f"    \"{item['rendering_text']}\"")
    print("=" * 72)

    findings = []
    is_clean = ask_yn(
        "\nDoes the Spanish rendering fully and accurately convey the meaning above, "
        "in first person and appropriate register?"
    )

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
                "\nSeverity — could a clinician or patient reasonably act differently "
                "because of this? (a dosage, frequency, negation, allergy, laterality "
                "or symptom-onset error is almost always CRITICAL)"
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
    p.add_argument("--items", required=True, type=Path, help="The master items JSONL (same file your teammate used)")
    p.add_argument("--out", required=True, type=Path, help="Output JSONL of your labels (appended, resumable)")
    args = p.parse_args()

    all_items = load_jsonl(args.items)
    if not all_items:
        print(f"No items found in {args.items}. Nothing to do.")
        return 1

    already_labeled = {r["id"] for r in load_jsonl(args.out)}
    en_to_es = [
        it for it in all_items
        if it.get("direction") == "en_to_es" and it["id"] not in already_labeled
    ]

    if not en_to_es:
        print("No en_to_es items left to label. Either none exist, or you've finished them all.")
        return 0

    print(f"\n{len(en_to_es)} item(s) ready for you. Ctrl-C anytime to stop safely.\n")

    done = 0
    try:
        for it in en_to_es:
            label = label_one_item(it)
            append_jsonl(args.out, label)
            done += 1
            print(f"\nSaved. ({done}/{len(en_to_es)} this session)")
    except KeyboardInterrupt:
        print(f"\n\nStopped early. {done} label(s) saved this session — re-run to resume where you left off.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
