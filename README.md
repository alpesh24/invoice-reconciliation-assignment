# Invoice Reconciliation & Review Platform


## Overview

A small local accounts-payable review app. It reads supplier invoice images (PNG), extracts the printed
fields with a vision model (Gemini), validates and normalizes them in code, matches each invoice to a
purchase order (PO) and receipt by exact reference, and computes expected vs billed amounts in code. It flags
duplicates and discrepancies and leaves unsupported cases `unresolved`. A reviewer opens the queue in a
Streamlit UI, compares the original image with the extracted fields and matched records, corrects an
extracted value (the original extraction stays visible), reruns reconciliation and saves a review status.
The model also drafts a short discrepancy note per non-reconciled invoice and one insight sentence, only from
verified findings. Notes are drafts, not decisions.

The model only reads and phrases. All arithmetic, matching, duplicate detection, and status logic is
deterministic Python.

## Quick start (no API key needed)

Requirements: Python 3.11+ (developed and tested on Python 3.12.10 on Windows 11). The default mode is
`MODEL_MODE=replay`, which reads saved real model responses from `data/model_cache/`; no key and no network
are needed.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                        # also installs src/ in editable mode
cp .env.example .env                                   # optional; blank values mean replay defaults

pytest                                                 # always uses replay, no network
python -m invoice_recon.cli run                        # process all 8 documents from the cache
python -m invoice_recon.cli reconcile                  # recompute from saved extractions, no model calls
streamlit run app/streamlit_app.py                     # review UI
python -m invoice_recon.cli reset --yes                # delete data/state/ (keeps data/model_cache/)
python scripts/compute_expected.py                     # regenerate data/expected/ from structured records
python scripts/check_report.py                         # writes reports/check-results.md
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
```

Activation is optional; `.\.venv\Scripts\python.exe` works directly. Run `pytest` from the venv: another
Python with an older `streamlit` can fail the UI test (this happened once during development).

`.env.example` lists variable names only. Blank or unset `MODEL_MODE` means `replay`; blank or unset
`USE_SIMULATIONS` means `1`. Variables already set in the environment take precedence over `.env`.

What to expect from a fresh clone in replay mode (checked on 2026-10-09 in a fresh replay run with no
`GEMINI_API_KEY`, after `cli reset --yes`; the earlier state was backed up and restored afterwards): `pytest` passes (122 tests), and `cli run` processes all 8 documents with no extraction
failures: reconciled 1, duplicate 1, unresolved 3, discrepant 3, recoverable USD 30.00. Extraction sources are
`cached` for seven images and `simulated` for `correction` (by design, see below). Notes: all 7 non-reconciled
invoices get a draft that passes the number guard, and all 7 notes plus the insight are saved real model
responses (`cached`); the cache holds 7 extraction, 7 note and 1 insight entries (the same fresh replay run
was repeated after the live run, again with no key).

The current dataset is fully covered by the cache. Only images added later need one live extraction: in replay
mode (no model calls), an image with no cache entry shows "extraction failed" and the batch continues.

## Running with live model calls

Set these in `.env` (never commit it; it is in `.gitignore`):

```
GEMINI_API_KEY=<your key>
GEMINI_MODEL=gemini-2.5-flash
MODEL_MODE=live
```

Then `python -m invoice_recon.cli run`. Each new live response is written to `data/model_cache/`
(`extract/`, `note/`, `insight/`) and is replayed afterwards. A live `run` makes one extraction call per image
that has no cache entry, one note call per non-reconciled invoice that has no cached note, and one call for the
insight. Notes and the insight are only drafted after the batch is reconciled, so they cover the final
findings. The free-tier quota is small; use `live` only when needed. Calls use a 60 s timeout and up to 2
retries with backoff on transient errors. Invalid JSON or schema errors become a visible `failed` extraction
with the error text; nothing is repaired silently. The key is read only from the environment and is never
logged.

## Replaying saved real responses

- `MODEL_MODE=replay` (the default) reads only from the cache and makes no call.
- Extraction cache key: `sha256(image bytes + prompt version + model)`. File:
  `data/model_cache/extract/<key>.json` (metadata, raw response text, parsed object). `clean.png` and
  `duplicate.png` are byte-identical, so they share one entry. Duplicate detection uses extracted fields, never
  image hashes. Note and insight entries use a hash of the findings payload + prompt version + model.
- A cache miss for an image gives `extraction.status = failed` with a clear error; the batch continues.
- Provenance labels (shown in the UI and saved in state): `live` (response fetched in this run), `cached`
  (a saved real response), `simulated` (data created by us, never a real model response). Simulated items are:
  - `data/simulations.json`: the `correction` image really shows `PO-5`; a simulated extraction reads it as
    `PO-S` so the correction flow (M5) has something to correct. The real cached response for that image is
    kept.
  - Deterministic note templates, used in replay only when no cached note exists for a findings payload (not
    needed for the current dataset).
  - `SIMULATED_FAILURES=file_id,...` forces an API failure for listed documents to show that the batch
    continues. `USE_SIMULATIONS=0` turns the `data/simulations.json` entries off.

## Architecture

```
input images -> ingest -> extract (per document, cached) -> normalize (+ corrections) -+
reference data (POs, receipts) ------------------------------------------------------+
                                                                                       v
                                 reconcile_batch (pure, whole batch, ingest_seq order)
                                                                                       v
                                  notes (non-reconciled only, cached) -> data/state/ -> UI
```

| Module (`src/invoice_recon/`) | Role |
|---|---|
| `config.py` | paths, env, prompt versions, Gemini settings |
| `models.py` | Pydantic models for the three layers (raw, normalized, saved state), PO/receipt, results |
| `money.py` | `Decimal` parsing to integer cents |
| `reference.py` | loads POs and receipts (flat seed format and lines format) |
| `documents.py` | discovers images, assigns persisted ingest order |
| `extraction/` | Gemini provider, cache, simulations, service |
| `normalize.py`, `matching.py`, `reconcile.py` | pure functions: validation, exact matching, findings, statuses |
| `notes.py`, `insights.py` | note drafting with number guard; deterministic aggregates plus model wording |
| `storage.py`, `pipeline.py`, `cli.py` | atomic JSON state, orchestration, CLI |
| `app/streamlit_app.py` | queue, invoice detail, summary, correction form |

Reconciliation always runs over the whole batch, because duplicate detection is cross-invoice. I/O lives only in
storage, the extraction providers, the CLI and the UI. Application code never reads the invoice answer key.
Full details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Model configuration

| Item | Value |
|---|---|
| Provider / SDK | Google Gemini via `google-genai==2.29.0` |
| Model ID | `gemini-2.5-flash` (set with `GEMINI_MODEL`; recorded in every cache entry) |
| Temperature | 0 |
| Extraction output | `response_mime_type=application/json`, `response_schema=RawExtraction` |
| Notes/insight output | plain text, no schema, temperature 0 |
| Max output tokens | 2048 (all calls) |
| Timeout/retries | 60 s, up to 2 retries with backoff on transient errors |
| Prompt versions | `extract-v1`, `note-v1`, `insight-v1` in `prompts/` (version is part of the cache key) |
| Confidence | none requested (self-reported confidence is not calibrated) |

The model returns every value as a string exactly as printed; code converts to cents. Absent, unreadable or
placeholder fields are `null` plus a warning, never inferred. Settings live in `src/invoice_recon/config.py`.

## Business rules, rounding and statuses

Source of truth: [data/inputs/domain.md](data/inputs/domain.md). Decisions: [docs/DECISIONS.md](docs/DECISIONS.md).

- **Rounding:** money is integer USD cents everywhere. Printed amounts are parsed with `decimal.Decimal`, never
  `float`. More than two decimals is a validation error. Nothing is ever rounded: expected = integer quantity x
  integer cents, so rounding is never needed.
- **Matching:** exact only. Invoice to PO by `(supplier_id, po_id)`; invoice line to PO line by exact SKU within
  that PO; receipt by `(po_id, sku)`. No fuzzy matching, no matching by amount. Missing, conflicting or ambiguous
  references are `unresolved`.
- **Expected** = ordered quantity x agreed unit price; **billed** = printed line/invoice total;
  **difference** = billed - expected (positive = overcharge). Billed quantity is compared with ordered and
  received quantity.
- **Duplicate:** same `(supplier_id, invoice_number)` as an earlier-processed valid invoice. Original vs duplicate
  is decided by processing order (`ingest_seq`, assigned once and persisted), not by order on disk.
- **Status precedence (first match wins):** `extraction_failed` -> `invalid` -> `duplicate` -> `unresolved` ->
  `discrepant` -> `reconciled`.
- **Totals:** `recoverable_cents` = sum of positive differences of `discrepant` invoices only. Duplicates,
  unresolved, invalid, and failed invoices never contribute.
- **Corrections** are applied to the raw string values and pass the same normalization; the original extraction is
  immutable, and the correction history is kept.

## Data

- **Seed** (`data/inputs/`, read-only, supplied): 4 invoice images (`clean`, `duplicate`, `wrong-price`,
  `missing-reference`), POs, receipts, `domain.md`, expected seed results. `clean.png` and `duplicate.png` are
  byte-identical.
- **Generated** (`data/generated/`): 4 more invoices (`multi-line-price`, `correction`, `conflicting-supplier`,
  `short-receipt`), POs PO-3..PO-5 and receipts RC-3..RC-5 in lines format, so the demo set has 8 invoices.
  Method: values were written by hand (no randomness, no seed), invoice records follow
  `invoice.template.json` extended from one SKU to a `lines` array, and `scripts/render_generated.py` renders
  both supplied layouts. Details and the mapping from template to lines format:
  [data/generated/GENERATION.md](data/generated/GENERATION.md).
- **Reference data for the app** is only purchase orders and receipts. The structured invoice records and
  expected results are read only by `tests/` and `scripts/`.
- **Processing order:** documents are discovered in `data/inputs/images/`, then `data/generated/images/`, by
  filename within a folder; `ingest_seq` is set at first processing and persisted, so documents added later get
  later numbers and a rerun never reorders.
- The data are fixtures for the rules; they do not establish real-world model accuracy.

## Reference cases and check results

Five reference cases cover the mandatory checks. Expected values were computed independently by
`scripts/compute_expected.py` (own code, no import from `src/`) from the structured records, and the seed results
are asserted against `data/inputs/expected-seed-results.json`. The Phase 6 dataset (including these five cases) was
approved by the user.

| ID | Case | Expected result |
|---|---|---|
| M1 | `clean` (INV-1, PO-1) | reconciled; expected 100.00, billed 100.00, difference 0 |
| M2 | `wrong-price` (INV-2, PO-2) | discrepant; expected 100.00, billed 120.00, difference +20.00 (matches the worked example in `domain.md`) |
| M3 | `duplicate` (INV-1 again) | duplicate; not payable; excluded from totals |
| M4 | `missing-reference` (INV-3) | unresolved; no PO matched; expected and difference null |
| M5 | `correction` (INV-12) | simulated misread `PO-S` is unresolved; correcting `po_id` to `PO-5` gives reconciled, 310.00 / 310.00 / 0, still present after restart |

Extra cases: `multi-line-price` (+10.00 on one line), `conflicting-supplier` (PO belongs to another supplier,
unresolved even though amounts equal that PO), `short-receipt` (billed equals ordered, received 4 of 6,
discrepant with difference 0).

`python scripts/check_report.py` runs the pipeline in replay mode, compares with `data/expected/` and writes
[reports/check-results.md](reports/check-results.md) (expected, observed, pass/fail, notes). Last result: 11 of 11
checks pass, no failures. Limitations of the checks are listed at the end of that report: the restart in M5 is
simulated by a fresh load from disk in the same process (the walkthrough below was also done by hand with
Streamlit), and the `correction` before-state comes from the simulation.

## Decisions and unresolved ambiguity

Decisions D1-D10, E1-E7, C1-C10 are in [docs/DECISIONS.md](docs/DECISIONS.md). The supplied rules leave these
points open; each was resolved without adding a business rule beyond the exercise rules:

| ID | Ambiguity | How it is handled |
|---|---|---|
| A1 | Received < ordered while billed = ordered | `short_receipt` finding, `discrepant`; difference stays as calculated (may be 0); no shortfall amount invented |
| A2 | Billed qty differs from ordered | `qty_over_ordered` / `qty_under_ordered`; amount per expected/billed rule |
| A3 | Printed qty x unit or sum of lines does not equal the printed total | billed = printed totals; `line_total_mismatch` / `invoice_total_mismatch` -> `discrepant` |
| A4 | "Conflicting reference" undefined | PO belongs to another supplier or PO-ID not found -> `unresolved` |
| A5 | Which of two identical invoices is the original | the one processed first (`ingest_seq`) |
| A6 | Both duplicate and discrepant | `duplicate` wins; difference not counted |
| A7 | PO line not billed | `po_line_not_billed`, `discrepant`, not added to expected |
| A8 | Matched PO line without receipt data | `no_receipt`, `unresolved` |
| A9 | Negative difference (undercharge) | shown, not in recoverable total |
| A10 | Same SKU twice on a PO or invoice | `ambiguous_sku`, `unresolved` |
| A11 | Several receipts for one `(po_id, sku)` or two POs with one id | `unresolved`; receipts never summed |
| A12 | Missing line description | allowed; does not affect validity (the seed images print none) |
| A13 | `supplier_id` null | `missing_reference`, `unresolved`; never a duplicate |
| A14 | Payable flag | `count_as_payable` is false only for duplicates; unresolved invoices keep it true but never contribute to totals |
| A15 | `qty_over_received` | kept as a finding (domain rule 3 compares billed with received quantity) |

## Known limitations

- Small demonstration set (8 invoices, one currency, one PO per invoice, mostly one or two lines): it exercises
  the rules but gives no evidence of real-world extraction accuracy. Out of scope per the brief: tax, partial
  billing, FX, payment terms, payments, authentication.
- The current dataset is fully covered by the cache (extractions, 7 notes, 1 insight). Images added later have no
  cached response and show "extraction failed" in replay until they are extracted once in live mode.
- Notes and the insight are cached live responses. Their cache key depends on the exact findings payload, so any
  change to the data, a correction that alters findings, or a new prompt version needs new live calls (one per
  non-reconciled invoice plus one for the insight, see "Running with live model calls"); without them replay uses
  the deterministic template, labelled `simulated`.
- The number guard checks that every `$X.XX` amount in a note exists in the findings payload. It does not check
  that the amount belongs to the right field or has the right sign.
- `check_report.py` counts payable invoices as reconciled plus discrepant invoices, not as the raw
  `count_as_payable` flag (which is also true for unresolved invoices, A14). The unresolved invoices are checked
  separately to stay out of the totals.
- Corrections are free-form (any field, any value, original preserved, history shown). The UI does not
  restrict them.
- One corrupt state file makes loading the whole batch fail with a storage error, instead of failing only that
  invoice (visible, but not per invoice).
- `tests/test_check_report.py` rewrites `reports/check-results.md` on every pytest run and cannot detect a
  mismatch itself; the pass/fail comes from `scripts/check_report.py`.
- Minor: a cache entry missing `model` or `raw_text` is not rejected; the insight fallback wording has no plural
  grammar ("count: 1, invoices affected: 1"); `use_container_width` is deprecated in Streamlit 1.65 but kept for
  older versions.

## Time spent

Recorded by the orchestrator in `docs/PROGRESS.md`. Times are wall-clock from the phase log and include review
rounds and waiting for approvals; the limit for the exercise is 8 hours.

| Phase | Time |
|---|---|
| 0 Setup | ~22 min |
| 1 Core domain | ~25 min |
| 2 Extraction | not recorded  |
| 3 Storage, pipeline, CLI | ~40 min |
| 4 UI | ~15 min |
| 5 Notes and insight | not recorded  |
| 6 Dataset extension | ~33 min |
| 7 Checks and report | ~18 min |
| 8 Documentation and AI config | ~22 min  |

Recorded phases add up to about 175 min; phases 2 and 5 have no recorded duration. The overall time budget
(including the data preparation outside these phases) should be confirmed by the author before submission.

## LLM usage note

- **Development tools:** Claude Code with a main orchestrator session and two project subagents, `implementer`
  and `reviewer` (`.claude/agents/`), both with `model: inherit`. Claude Code version 2.1.295; orchestrator model
  Sonnet 5.5 (`claude-sonnet-5-5`); both stated by the author (see `ai-workflow/manifest.json`). The skill
  `.claude/skills/verify-reconciliation` is kept but not used: it refers to scripts that do not exist here.
- **Application model:** Gemini `gemini-2.5-flash` for extraction, notes, and the insight sentence.
- **Generated by Claude Code:** the application, tests, scripts, dataset, and these docs, one phase at a time
  (implement, test, independent review, human approval). Review outputs are saved in `ai-workflow/reviews/`.
- **Representative instruction:** run Phase 3 (storage, pipeline, CLI) through the implement-test-review loop under
  the rules in `CLAUDE.md`.
- **Correction/verification:** the Phase 3 end-to-end run made all four seed invoices `invalid` because rule A12
  required a line description and the seed images print none. The user decided to allow a null description; A12,
  `ARCHITECTURE.md` and `normalize.py` were changed (snapshots in `ai-workflow/snapshots/`). Other catches:
  Phase 4 review found a UI test that failed on an older Streamlit; Phase 7 found the expected file and the
  application disagreeing on `count_as_payable` (A14).
- **Verification of results:** expected values come from `domain.md`, the seed files, and
  `scripts/compute_expected.py`, never from application output. Details: `ai-workflow/`.

## AI configuration

See [ai-workflow/README.md](ai-workflow/README.md) and [ai-workflow/manifest.json](ai-workflow/manifest.json).

## Presentation

Written walkthrough (no recording or slides). After `pip install` and `python -m invoice_recon.cli run`, start
`streamlit run app/streamlit_app.py` and:

1. Queue: filter by status. The counts match the table above (reconciled 1, discrepant 3, duplicate 1,
   unresolved 3).
2. Open `wrong-price`: the image sits beside the extracted fields; the PO and receipt are shown; the line table
   shows agreed 20.00 vs billed 24.00 and a difference of 20.00. The draft note is labelled by provenance.
3. Open `correction`: the extraction is labelled `simulated` (`po_id` = `PO-S`, unresolved). Enter a correction
   `po_id` = `PO-5` with a reason, save: reconciliation reruns for the whole batch and the invoice becomes
   reconciled; the original value and the correction history stay visible.
4. Stop and restart Streamlit: the correction and review status are still there (saved in `data/state/`).
5. Summary: counts, recoverable total (USD 30.00, discrepant invoices only), and the insight text.
