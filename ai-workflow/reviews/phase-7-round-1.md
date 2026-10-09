PHASE: 7  ROUND: 1  BASE: .baseline/
VERDICT: PASS
MECHANICAL CHECKS:
- K1 pass — `baseline.py status data/inputs/` printed nothing.
- K2 pass — `env -u GEMINI_API_KEY MODEL_MODE=replay pytest -q` gave 122 passed.
- K3 pass — grep over src/ and app/ found no hits.
- K4/K5 pass — no changes to money.py, normalize.py, matching.py or reconcile.py in the diff. The existing `qty_over_received` logic in reconcile.py is unchanged.
- K6 pass — only src/invoice_recon/extraction/gemini.py matches (plus its .pyc files).
- K7 not run — .gitignore and the key search were not re-checked this phase, and the diff touches neither.
- K8 pass, with one justified hit — the only removed assert is the test_dataset.py line `line_findings == {"CAB-1": ["short_receipt"]}`. It was replaced by a stricter, sorted assert expecting ["qty_over_received", "short_receipt"]. Hand check: ordered 6, received 4, billed 6. No skip or xfail added.
- K9 pass — no prompt changes.
- K10 n/a — no app/ changes.
CHECKPOINT: met. reports/check-results.md shows 11 of 11 passing, M1–M5 rows, extra cases, limitations, summary and batch-resilience checks.
FINDINGS:
- #1 [minor] tests/test_check_report.py:11 — The test overwrites reports/check-results.md (timestamped) on every pytest run and asserts only exit code and "FAIL" absence. Nothing proves the report detects a mismatch. Fix: add a small unit test of compare()/observe() with a deliberately wrong value; consider writing the report to tmp.
- #2 [minor] scripts/check_report.py:178 — The M3 totals check recomputes the payable count with status in (reconciled, discrepant), different from plain count_as_payable after A14 (unresolved are now true). Harmless but may confuse; add a one-line note in the report.
NOTES:
- Answer key: expected values only from data/expected/expected-results.json (compute_expected.py). Observed from pipeline.run_pipeline, add_correction, reconcile_all, storage.load_all. Only mapping: price_diff→price_differs.
- M5 reloads from disk (load_all/load_summary after add_correction, then fresh run_pipeline + reconcile_all and reload); checks raw extraction immutable, correction history, other invoices unchanged.
- Report runs in a tempfile state dir; MODEL_MODE forced to replay before import; no live call.
- data/state/ mtimes 10:46 (before review); no Phase 7 code writes there; contents could not be confirmed unchanged (outside baseline).
- Oracle changes justified: qty_over_received by domain.md rule 3 (A15); count_as_payable false only for duplicates (A14), consistent with ARCHITECTURE. Checks not weakened.
- test_notes.py: MODEL_CACHE_DIR monkeypatched to tmp; hermetic; effective only if notes code reads config at call time (tests pass).
- Process steps (snapshot, workflow-log) not verified beyond seeing the files.
