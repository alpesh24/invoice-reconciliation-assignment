PHASE: 1  ROUND: 1  BASE: .baseline/
VERDICT: PASS
MECHANICAL CHECKS:
- K1 pass: `baseline.py status data/inputs/` printed nothing.
- K2 pass (with the package importable): `pytest -q` run with the system Python collects 0 tests because `invoice_recon` is not installed there (ModuleNotFoundError). With `PYTHONPATH=src` and no GEMINI_API_KEY, 52 passed. `.venv` has the editable install and imports the package. Run `pytest` from the activated venv. The system-Python failure is an environment issue, not a code problem.
- K3 pass: no hits in src/ or app/.
- K4 pass: the only hit is the docstring "never float" in money.py.
- K5 pass: the only hit is the word "fuzzy" in the matching.py docstring ("no fuzzy logic"). No fuzzy code.
- K6 pass: no hits, so no model calls.
- K7 pass: .gitignore lists `.env` and `.baseline/`. I did not run the AIza key grep; the Phase 1 diff touches no secrets.
- K8 pass: the tests/ diff shows no removed asserts, skips or xfails. All three test files are new.
- K9 pass: no prompt changes.
- K10 n/a: no app/ code in this phase.
CHECKPOINT: met. tests/test_seed.py builds RawExtraction from seed.json["invoices"] (tests only) and runs normalize then reconcile_batch. It reproduces all four expected results from expected-seed-results.json with no model call: clean reconciled 10000/10000/0, wrong-price discrepant 10000/12000/+2000, duplicate with count_as_payable false, and missing-reference unresolved with null expected and difference.
PREVIOUS FINDINGS: none (round 1)
FINDINGS:
- #1 [minor] src/invoice_recon/normalize.py:91 — rule 9 — apply_corrections raises ValueError for a correction that targets a missing line or an unknown field. In Phase 3 this must not crash a batch rerun. — The pipeline should catch it and show it as a visible per-invoice problem, or reject the correction when it is saved.
- #2 [minor] src/invoice_recon/reconcile.py:129 — C4 — In reconcile_batch, an item with extraction_ok=True and normalized=None is reported as `invalid` with empty errors. This is harmless for now, but the pipeline should never produce it. — Add an explicit error text such as "no normalized data".
NOTES: Hand check of wrong-price: expected 5 x 2000 = 10000, billed 12000, difference +2000; price_diff and recoverable behave as expected. Decisions A11–A13 are implemented: ambiguous_receipt and ambiguous_po give unresolved, missing description is an error, and null supplier_id gives missing_reference and is never a duplicate. Duplicate ordering uses ingest_seq (the test shuffles list order) and recoverable_cents counts only positive differences of discrepant invoices.
