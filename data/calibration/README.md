# The 40-item calibration bank

`items.jsonl` — 40 unlabeled source/rendering pairs, ready for the tools in
`../../tools/`. Composition matches `misc/SETUP.md` §6.4 exactly, split
evenly across both directions:

| bucket | es_to_en (`eng-*`, you) | en_to_es (`esp-*`, teammate) |
|---|---|---|
| clean | 6 | 6 |
| single critical | 5 | 5 |
| single non-critical | 5 | 5 |
| multi-error | 2 | 2 |
| ambiguous | 2 | 2 |

No bucket or intended-error field is in `items.jsonl` — only content. Do
not open `raw/answer-key-DO-NOT-OPEN-BEFORE-LABELING.md` until you and your
teammate have both finished labeling; it's there to sanity-check afterward,
not to guide you, and it's gitignored so it never leaves this machine.

## Run it

```bash
python3 ../../tools/label_quiz.py --items items.jsonl --out my_labels.jsonl
```

Hand the same `items.jsonl` (unmodified) to your bilingual teammate:

```bash
python3 ../../tools/label_quiz_es.py --items items.jsonl --out my_labels_es.jsonl
```

Then merge and split per `misc/SETUP.md` §6.6 once both files are complete.
