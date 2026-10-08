# Invoice Reconciliation & Review — instructions for Claude Code

## What this project is

A take-home assignment (Junior AI Engineer, "Alternative B: Invoice reconciliation"). A small local
accounts-payable review app for a **fictional** business:

1. Read supplier invoice images (PNG/JPEG).
2. Extract fields with a vision LLM (Gemini).
3. Validate and normalize the extraction in code.
4. Match invoices to purchase orders and receipts; compute expected vs billed amounts in code.
5. Detect duplicates, flag discrepancies, keep unsupported cases unresolved.
6. Let a reviewer inspect evidence, correct extracted fields, rerun reconciliation, and save review state.
7. Draft short discrepancy notes with the LLM from verified findings only.

There is a hard **8-hour limit** for the whole exercise, including data preparation and documentation.
Prefer simple, working and verified over complete or clever.

## Read before working

| File | When |
|---|---|
| `data/inputs/domain.md` | Always. **Source of truth for business rules.** |
| `docs/SPEC.md` | Requirements, the five mandatory checks, submission checklist |
| `docs/ARCHITECTURE.md` | Pipeline, schemas, storage layout, statuses, replay mode |
| `docs/DECISIONS.md` | Decisions already made and known ambiguities. Do not re-decide these. |
| `docs/PLAN.md` | Implementation phases. Work on one phase at a time. |
| `docs/DATASET.md` | Only for the dataset-extension phase |

## Non-negotiable rules

1. **No invented business rules.** Rules come only from `data/inputs/domain.md` and `docs/DECISIONS.md`.
   Do not add real-world accounting, tax, or industry policy. If something is unclear, stop, add it to
   "Open questions" in `docs/DECISIONS.md`, and ask.
2. **Money is integer USD cents everywhere.** Parse printed amounts with `decimal.Decimal`, never `float`.
   More than two decimals is a validation error. Never round.
3. **The model only reads and phrases.** It extracts printed text and words notes and insights.
   All arithmetic, matching, duplicate detection and status logic is deterministic Python.
4. **Exact matching only.** Invoice → PO by exact `(supplier_id, po_id)`. Invoice line → PO line by exact
   SKU within the matched PO. No fuzzy matching, no matching by amount, no "closest" record.
   Missing, conflicting or ambiguous references → `unresolved`.
5. **`data/inputs/` is read-only.** Never modify, move, regenerate or re-render anything there. Never run
   `data/inputs/render_invoices.py`.
6. **Answer-key separation.** Application code (`src/`, `app/`) must never read `seed.json["invoices"]`,
   `invoice.template.json`, `expected-seed-results.json`, `data/generated/invoice-records.json` or
   anything in `data/expected/`. Reference data for the app is only purchase orders and receipts.
   Only `tests/` and `scripts/` may read expected results or structured invoice records.
7. **Never use application output as the answer key.** Expected results come from
   `scripts/compute_expected.py`, which computes them independently from structured records.
8. **The original extraction is immutable.** Reviewer corrections are an overlay with history.
9. **A batch never stops on one failure.** API errors, invalid JSON, unreadable images and validation
   errors become visible per-invoice statuses.
10. **Label provenance.** Every model response is marked `live`, `cached` or `simulated`. Never present
    simulated data as a real model response.
11. **Secrets only from `.env`.** Never commit, log or print API keys. `.env` is gitignored.
12. **Notes are drafts.** No wording that implies fraud or wrongdoing; a discrepancy is a difference to review.
13. **English** for code, comments, UI, docs and generated notes.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # then fill in values

python -m invoice_recon.cli run          # process all documents (MODEL_MODE from .env)
python -m invoice_recon.cli reconcile    # recompute from saved extractions, no model calls
python -m invoice_recon.cli reset --yes  # delete data/state/ (keeps model cache)
streamlit run app/streamlit_app.py       # review UI
pytest                                   # always runs with MODEL_MODE=replay
python scripts/compute_expected.py       # regenerate data/expected/ from structured records
python scripts/check_report.py           # writes reports/check-results.md (expected vs observed)
```

`MODEL_MODE` defaults to `replay`. Use `live` only when asked, or when a cache entry is missing and the
user approves the call (free-tier quota).

## How to work

- Follow `docs/PLAN.md` phase by phase. At the end of each phase: run `pytest`, show the checkpoint
  result, commit, then stop and wait for review before starting the next phase.
- Small commits with descriptive messages. Commit changes to `CLAUDE.md`, `docs/`, `prompts/` and
  `.claude/` **separately** from code — they are AI configuration whose history is part of the submission.
- Prompts live in `prompts/` with the version in the filename (`extract-v1.md`). Changing a prompt means a
  new file and a new `PROMPT_VERSION`; never edit a prompt that has produced cached responses.
- After a significant instruction, generated component, or correction, append a short entry to
  `ai-workflow/workflow-log.md` (instruction, what was produced, how it was checked, what was corrected).
- Pin versions in `requirements.txt`. Say why before adding a dependency.
- Do not start optional features (PDF input, export, decision history) until all five mandatory checks pass.
- When unsure whether something is in scope, check `docs/SPEC.md`; if still unsure, ask.

## Code style

- Python 3.11+, type hints, Pydantic v2 models.
- Normalization, matching, reconciliation and dedupe are small **pure functions** with no I/O.
- I/O lives only in `storage.py`, extraction providers, the CLI and the UI.
- `pathlib` for paths, all paths relative to the repo root via `config.py`. No global mutable state.
- Tests: pytest, deterministic, no network.
