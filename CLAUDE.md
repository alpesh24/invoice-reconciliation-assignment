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
| `docs/PROGRESS.md` | **First thing in every session** — current phase and loop state |
| `docs/REVIEW_CHECKLIST.md` | Used by the reviewer; know what will be checked |

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

## How to work: the implement → test → review loop

The main session is the **orchestrator**. It does not write application code itself. It delegates to two
subagents in `.claude/agents/`:

- `implementer` — implements one phase or fixes review findings. Never commits, never calls a model live.
- `reviewer` — independent, read-only. Checks the diff against `docs/REVIEW_CHECKLIST.md`, the rules above
  and the phase checkpoint. Returns `PASS` or `CHANGES_REQUESTED` with numbered findings.

### Loop protocol (per phase)

1. **Orient.** Read `docs/PROGRESS.md`. Continue the phase recorded there; otherwise take the next phase
   from `docs/PLAN.md`.
2. **Start.** Record the base commit (`git rev-parse HEAD`) and start time in PROGRESS.md.
3. **Implement.** Call `implementer` with: phase number, round number, and any notes from the user.
4. **Test gate.** Run `MODEL_MODE=replay pytest -q`. If red, send the failure output back to `implementer`.
   After 3 failed test-fix attempts, stop and ask the user.
5. **Review.** Call `reviewer` with: phase number, round number, base commit, and previous findings
   (round 2+). Do **not** pass the implementer's reasoning or report — the review must be independent.
6. **Save evidence.** Save the reviewer output verbatim to `ai-workflow/reviews/phase-<n>-round-<m>.md`.
7. **Decide.**
   - `CHANGES_REQUESTED` → send the blocker and major findings to `implementer` as the next round.
     **Maximum 3 review rounds per phase.** After round 3, stop and report the open findings to the user.
   - If the implementer disputes a finding, pass the dispute to the reviewer in the next round. If they
     still disagree, ask the user.
   - `PASS` → record minors under "Deferred minor findings" in PROGRESS.md and continue.
8. **Commit.** First the code (`phase <n>: <summary>`), then review files, PROGRESS.md and workflow log
   (`phase <n>: review evidence`).
9. **Report and stop.** Update PROGRESS.md (status, final commit, rounds, finish time). Append to
   `ai-workflow/workflow-log.md` if a review caught something real or a decision was made. Tell the user:
   what was built, checkpoint result, review rounds and what they caught, deferred minors, time spent.
   **Wait for approval before the next phase.**

### Loop rules

- **Phase 0 skips the reviewer** (setup only): implement → test gate → commit → report.
- **Open questions:** if the implementer reports one, stop the loop and ask the user. Record the answer in
  `docs/DECISIONS.md` (decision table, not "Open questions") before continuing.
- **Live model calls** (`MODEL_MODE=live`) are made only by the orchestrator, only after the user approves,
  and only for the steps PLAN.md names. Cached responses are committed with the phase.
- **Config changes** (`CLAUDE.md`, `.claude/`, `docs/`, `prompts/`) are committed separately from code,
  with a message saying what changed and why. Their history is part of the submission.
- Prompts live in `prompts/` with the version in the filename. Changing a prompt means a new file and a new
  `PROMPT_VERSION`; never edit a prompt that has produced cached responses.
- Pin versions in `requirements.txt`. New dependencies need a one-line reason.
- Do not start optional features until M1–M5 pass.

## Code style

- Python 3.11+, type hints, Pydantic v2 models.
- Normalization, matching, reconciliation and dedupe are small **pure functions** with no I/O.
- I/O lives only in `storage.py`, extraction providers, the CLI and the UI.
- `pathlib` for paths, all paths relative to the repo root via `config.py`. No global mutable state.
- Tests: pytest, deterministic, no network.