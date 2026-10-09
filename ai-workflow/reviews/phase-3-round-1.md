PHASE: 3  ROUND: 1  BASE: .baseline/ (last approved phase)
VERDICT: PASS
MECHANICAL CHECKS:
- K1 pass — `baseline.py status data/inputs/` printed nothing.
- K2 pass (with caveat) — `.venv/Scripts/python.exe -m pytest -q` gave 84 passed. A bare `pytest` on the system Python 3.11 fails collection with `No module named invoice_recon`. With PYTHONPATH=src it gives 83 passed and 1 failed, because the system Python lacks the google package (test_gemini_generate_config_settings). Both failures come from the environment, not the code.
- K3 pass — no hits in src/ or app/.
- K4 pass — the only hit is the word "float" in the money.py docstring ("never float").
- K5 pass — the only hit is the word "fuzzy" in the matching.py docstring.
- K6 pass — only src/invoice_recon/extraction/gemini.py (plus its .pyc).
- K7 pass — .gitignore lists `.env` (line 1) and `.baseline/` (line 8). I did not run the AIza key search.
- K8 pass — no weakened asserts and no skip/xfail in the tests diff.
- K9 pass — no changes under prompts/.
- K10 n/a — there is no app/ yet.
CHECKPOINT: met. test_end_to_end_replay_from_cache runs the real pipeline on the images through the replay cache. It matches expected-seed-results (clean reconciled, wrong-price discrepant +2000, duplicate of clean, missing-reference unresolved) and recoverable 2000. Ingest order is persisted, and later documents get later seq. A second run in reversed order does not reorder anything. Corrections and review survive both `run` and `reconcile`. A correction is still there after reloading state from disk. I did not run the CLI by hand, to avoid writing data/state.
PREVIOUS FINDINGS: none (round 1)
FINDINGS:
- #1 [minor] src/invoice_recon/storage.py:68 — Rule 9 — `load_all` raises StorageError on one corrupt invoice file, so `run` and `reconcile` abort for the whole batch. The CLI shows a clear error, so this is visible and not silent. Consider reporting the corrupt file as a per-invoice failure in Phase 4, or leave as is and note it.
- #2 [minor] src/invoice_recon/reference.py:29 — typo `subset ={` (formatting only).
NOTES: Rules 8, 9 and 10 look right. The raw extraction is never mutated, corrections are an append-only overlay, and a failing extractor or a bad saved correction becomes a visible status. A12 is consistent: the description-missing error is removed from normalize.py.
Hand check: wrong-price is 5 × 20.00 = 100.00 expected against 120.00 billed, so +2000. The test fixes this to 0 by correcting unit price, line total and invoice total.
Run pytest from the .venv, or add `pythonpath = ["src"]` to pyproject.toml, so the documented bare `pytest` works.
