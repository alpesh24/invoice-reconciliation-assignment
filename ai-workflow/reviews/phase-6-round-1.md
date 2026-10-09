PHASE: 6  ROUND: 1  BASE: .baseline (no git)
VERDICT: PASS
MECHANICAL CHECKS:
- K1 pass — `baseline.py status data/inputs/` is empty.
- K2 pass — 121 passed (replay, no key).
- K3 pass — no hits in src/ or app/. The app reads only seed.json and generated/reference.json (pipeline.py:30).
- K4/K5/K6/K7/K9/K10 not run, no src/app/prompts files changed. K4/K5 are n/a for the same reason. I did not check K7 (.gitignore, key search) at all.
- K8 pass — the tests diff has no removed asserts and no skips. tests/test_dataset.py is new (A).
CHECKPOINT: met on the artifacts. Reference data, records, renderer, 4 images, GENERATION.md, simulations.json and expected-results.json all exist. The user has not yet inspected the five reference cases; PROGRESS.md already lists this as pending user action.
FINDINGS:
- #1 [minor] data/generated/GENERATION.md — The doc says replay shows the new images as "extraction failed" until live extraction is run. That is correct and was disclosed, but the live extraction step (ask first) is still pending. The orchestrator must ask before running it and keep the notes/insight live run after it.
NOTES: I recomputed the expected values by hand from reference.json and the invoice records, and they match.
- multi-line-price: expected 10×2000 + 4×1500 = 26000, billed 27000, diff +1000.
- short-receipt: expected 3×4500 + 6×1800 = 24300, billed 24300, diff 0, with a CAB-1 short_receipt finding.
- correction: unresolved before (PO-S), 31000/31000/0 reconciled after.
- conflicting-supplier: unresolved.
- Batch totals are 1/3/1/3 before and 2/3/1/2 after, with recoverable 3000, all as DATASET.md specifies.
compute_expected.py has no src import and cross-checks its seed results against expected-seed-results.json. Rerunning it reproduces the file unchanged. Image short-receipt.png renders correctly. The simulation record only changes po_id to PO-S, as specified.
