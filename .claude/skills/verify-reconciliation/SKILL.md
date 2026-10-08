---
name: verify-reconciliation
description: Verify reconciliation changes before declaring done.
---
Never report a change as complete based on the edit alone.
1. Run `pytest -q` — all tests must pass.
2. Run `python scripts/eval.py` — match accuracy must be >= 98%, zero false matches.
3. Run ruff/mypy — no new errors.
If any step fails, fix and rerun from step 1.