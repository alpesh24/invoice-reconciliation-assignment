# Phase 5 — Round 1 — reviewer output

PHASE: 5  ROUND: 1  BASE: .baseline/ (last approved phase)
VERDICT: PASS

MECHANICAL CHECKS: K1-K10 all pass (116 tests passed; no answer-key reads in src/app; no float money; model reached only via gemini.py provider; .env/.baseline ignored; no removed asserts; prompts edited in place were placeholders with no cache entries; app does no business logic).

CHECKPOINT: met — in replay, wrong-price (discrepant), duplicate and missing-reference (unresolved) each get a guarded draft note; clean gets none. Notes labelled `simulated` (deterministic template), guard_passed true.

FINDINGS:
- #1 [minor] notes.py:57-63 — guard checks that each amount appears somewhere in the payload, not that it is the right amount for the right field; ignores sign. Acceptable for the phase; document the limit in README (Phase 8).
- #2 [minor] pipeline.py:90-106 — attach_notes runs on every _save_all, so a live `run` with a key makes one call per non-reconciled invoice plus one for the insight (cached by payload hash). reconcile/corrections pass no provider and never call a model. Correct; worth noting.

NOTES: PLAN item "Live run once (ask first), then cached" not done: no note/ or insight/ cache entries. Ask the user before the live run.
