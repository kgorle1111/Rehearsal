# tools — interactive calibration labelling

Solves the friction problem in `misc/SETUP.md` §6: instead of hand-filling a markdown table, run one item at a time and answer multiple-choice questions. Two scripts, one per direction, one per person:

| Script | Who runs it | Direction | Shows |
|---|---|---|---|
| `label_quiz.py` | You (English only) | `es_to_en` — patient speaks Spanish, rendered to English | English fact vs. English rendering |
| `label_quiz_es.py` | Your bilingual teammate | `en_to_es` — clinician speaks English, rendered to Spanish | English source vs. Spanish rendering, directly |

Both write the **same output schema**, so the two files merge cleanly for the dev/test split (§6.6).

## Try it first (demo, not real data)

```bash
python3 label_quiz.py --items demo_items.jsonl --out my_test_labels.jsonl
python3 label_quiz_es.py --items demo_items.jsonl --out my_test_labels_es.jsonl
```

Five illustrative items in `demo_items.jsonl` — not real calibration content. Delete the test output files when you're done trying it.

## The language split — why there are two scripts

- **`es_to_en` (you): you can label these directly.** The rendering you judge is in English; you compare it against the independent English fact the scenario was built from. `label_quiz.py` shows you these one at a time.
- **`en_to_es` (your teammate): needs a bilingual judgement, and there's no honest shortcut around it.** The rendering is in Spanish. Any English gloss a monolingual reviewer checked it against would just be confirming content someone already wrote, not an independent judgement — that's the same circularity the whole calibration protocol exists to prevent. `label_quiz.py` never shows you this content; it queues item IDs (content-free) into `needs-bilingual.jsonl` so you know they exist, then `label_quiz_es.py` reads the full items file directly for your teammate to work from.

This also satisfies `SETUP.md` §6.5 step 7 (a second labeller for inter-rater reliability) — one recruit covers both needs.

## Real usage — the workflow

1. **You run the English tool first**, on the full items file:
   ```bash
   python3 label_quiz.py --items your_items.jsonl --out my_labels.jsonl
   ```
   Resumable — Ctrl-C anytime, re-run to continue. `en_to_es` items are queued into `needs-bilingual.jsonl` (next to your items file) automatically, with no content shown.

2. **Hand your teammate the same master items file** (`your_items.jsonl`) — he does not need `needs-bilingual.jsonl` itself, that file was only your heads-up. He runs:
   ```bash
   python3 label_quiz_es.py --items your_items.jsonl --out my_labels_es.jsonl
   ```
   Same resumable behaviour, same taxonomy, same severity/confidence questions — just in his direction, with real content shown.

3. **Item file format** — one JSON object per line, both directions live in the same file:
   ```json
   {"id": "c07", "direction": "es_to_en", "fact_en": "Take one tablet twice a day with food.", "rendering_text": "Take one tablet once a day with food."}
   {"id": "c12", "direction": "en_to_es", "source_text": "Do not take this medication with alcohol.", "rendering_text": "No tome este medicamento con alcohol."}
   ```

## After labelling

`my_labels.jsonl` + `my_labels_es.jsonl` together are your 40 items. Merge them (just concatenate — same schema) and do the dev/test split in `misc/SETUP.md` §6.6 **once, after all 40 exist, before any tuning happens** — not before, not gradually.
