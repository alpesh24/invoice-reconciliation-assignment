# Implementation plan

Work one phase at a time. At the end of each phase: run `pytest`, show the checkpoint result, commit,
append to `ai-workflow/workflow-log.md` if something notable happened, and **stop for review**.
Times are a budget, not a target; total ≈ 8 h. If a phase overruns, say so and propose what to cut.

## Phase 0 — Setup (≈ 15 min)

- Create the layout from `ARCHITECTURE.md`. Starter files are already in `data/inputs/`; do not touch them.
- `requirements.txt` (pinned): `google-genai`, `pydantic>=2`, `streamlit`, `pillow`, `python-dotenv`, `pytest`.
- `.gitignore` (`.env`, `.venv/`, `data/state/`, `__pycache__/`, `.pytest_cache/`), `.env.example`.
- `config.py` with paths and env loading; `MODEL_MODE` defaults to `replay`.
- `ai-workflow/workflow-log.md` started.

**Checkpoint:** `pip install -r requirements.txt` works; `pytest` runs (0 tests is fine); git initialized,
first commit.

## Phase 1 — Core domain, no model (≈ 1.5 h)

- `models.py`, `money.py`, `reference.py` (flat + lines formats), `normalize.py`, `matching.py`,
  `reconcile.py` — pure functions.
- Unit tests: money parsing (incl. `"24.00"`, `"1,234.50"`, `"24.005"` → error), normalization validity
  rules, each matching outcome, each status, duplicate ordering, recoverable total.
- **Seed test:** in tests only, build `RawExtraction` objects from `seed.json["invoices"]`, run
  normalize → reconcile_batch, and compare with `expected-seed-results.json`.

**Checkpoint:** all four seed results reproduced from structured records, without any model call.
This proves the business logic independently of extraction.

## Phase 2 — Extraction (≈ 1.25 h)

- `prompts/extract-v1.md`; `extraction/` package: Gemini provider, cache, replay, simulations,
  `SIMULATED_FAILURES`.
- Validation of the model response against `RawExtraction`; failures saved with error text.
- **One live run** on the four seed images (ask before running), saving responses to `data/model_cache/`.
- Inspect the four responses by eye against the images and record the result in the workflow log.
- Tests (replay): cache hit, cache miss → `failed`, invalid JSON → `failed`, simulated failure does not
  stop the batch.

**Checkpoint:** with `GEMINI_API_KEY` unset and `MODEL_MODE=replay`, extraction of all seed images
works from cache.

## Phase 3 — Storage, pipeline, CLI (≈ 1 h)

- `storage.py` (atomic writes), `pipeline.py`, `cli.py` (`run`, `reconcile`, `reset --yes`).
- Corrections: add a correction → re-normalize → reconcile whole batch → save. Existing corrections and
  review state survive `run` and `reconcile`.
- Tests: ingest order is assigned once and persisted, documents added later get later `ingest_seq`, a second run does not reorder; end-to-end replay run reproduces seed expected results; a correction persists after reloading
  state from disk (simulates restart).

**Checkpoint:** `python -m invoice_recon.cli run` in replay mode produces state matching seed expectations.

## Phase 4 — UI (≈ 1.25 h)

- Queue, invoice detail, summary as described in `ARCHITECTURE.md`.
- Correction form → save → rerun → reload. Provenance badges. Review status and comment.

**Checkpoint:** manual walkthrough: filter by status, open wrong-price, correct a field, restart Streamlit,
correction still visible. Screenshot or short description in the workflow log.

## Phase 5 — Notes and insight (≈ 45 min)

- `prompts/note-v1.md`, `prompts/insight-v1.md`, `notes.py` with number guard, `insights.py` with
  deterministic aggregates and fallback text. Live run once (ask first), then cached.
- Tests: guard rejects a note containing an amount not in findings; notes only for non-reconciled invoices.

**Checkpoint:** every non-reconciled seed invoice has a guarded draft note in replay mode.

## Phase 6 — Dataset extension (≈ 45 min)

Follow `docs/DATASET.md` and `.claude/skills/generate-assignment-data/SKILL.md`.

- `data/generated/reference.json`, `invoice-records.json`, `scripts/render_generated.py`, rendered images,
  `GENERATION.md`, updated `simulations.json`.
- `scripts/compute_expected.py` → `data/expected/expected-results.json`, independent of `src/`.
- Ask the user to inspect the five reference cases by hand before continuing.
- Live extraction for the new images (ask first).

**Checkpoint:** user has confirmed the five reference cases; expected results file committed.

## Phase 7 — Checks and report (≈ 30 min)

- `scripts/check_report.py`: runs the pipeline in replay mode, compares with `data/expected/`, writes
  `reports/check-results.md` with M1–M5 rows plus the extra cases (expected, observed, pass/fail, notes).
- M5 check: apply the documented correction, reload state from disk, verify the recalculated result.
- Fix failures or document them.

**Checkpoint:** report committed; every failure explained.

## Phase 8 — Documentation and AI configuration (≈ 45 min)

- Complete `README.md` (all sections in the skeleton).
- Rename and complete `ai-workflow/README.template.md` → `README.md` and `manifest.template.json` →
  `manifest.json`: Claude Code version and model, this `CLAUDE.md` and `docs/` (with commits), prompts,
  skill, Gemini model and parameters, `not-used` for hooks/subagents/MCP, `.env.example` names, replay
  command, workflow example from the log.
- Time spent per phase in the README.

**Checkpoint:** a fresh clone, without an API key, can run `pytest`, `cli run` and the UI.

## Optional (only if time remains, in this order)

1. Export of the review queue and discrepancy calculations (CSV/JSON).
2. Reviewer decision and note revision history.
3. PDF input.
