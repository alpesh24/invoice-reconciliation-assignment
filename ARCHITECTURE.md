# Architecture

## Repository layout

```
CLAUDE.md
README.md
requirements.txt
.env.example                    # app variable names only, no values
.gitignore                      # .env, .venv/, data/state/, __pycache__/
.claude/skills/generate-assignment-data/SKILL.md   # copied from the starter pack (data phase only)

ai-workflow/                    # templates from the starter pack; completed at the end
  workflow-log.md               # running log of instructions, checks, corrections

data/
  inputs/                       # ORIGINAL starter files — read-only, never modified
    domain.md  seed.json  expected-seed-results.json  invoice.template.json
    render_invoices.py  PACK_README.md  images/*.png
  generated/                    # our additions (dataset phase)
    reference.json              # extra POs and receipts (lines format)
    invoice-records.json        # structured truth for generated invoices (tests/scripts only)
    images/*.png
    GENERATION.md               # method, script, seed, mapping
  simulations.json              # labelled simulated extractions / failures
  expected/expected-results.json   # computed by scripts/compute_expected.py
  model_cache/                  # saved real model responses — committed, used by replay
  state/                        # runtime state — gitignored, rebuilt by `cli run`

prompts/
  extract-v1.md
  note-v1.md
  insight-v1.md

src/invoice_recon/
  config.py        # paths, env (MODEL_MODE, GEMINI_MODEL, ...), PROMPT_VERSION constants
  models.py        # Pydantic models for all three layers + reference data + results
  money.py         # Decimal parsing → cents, formatting
  reference.py     # load POs/receipts (flat seed format + lines format)
  documents.py     # discover documents, assign ingest order for new ones
  extraction/
    base.py        # ExtractionProvider protocol, ExtractionResult
    gemini.py      # live provider
    cache.py       # read/write data/model_cache/
    simulated.py   # applies data/simulations.json
  normalize.py     # RawExtraction (+ corrections) → NormalizedInvoice
  matching.py      # invoice → PO, lines → PO lines, receipts
  reconcile.py     # findings, amounts, statuses, batch totals (pure)
  notes.py         # note drafting + number guard
  insights.py      # deterministic aggregates + model wording
  storage.py       # atomic JSON read/write of data/state/
  pipeline.py      # orchestration: extract → normalize → reconcile → notes → save
  cli.py           # run / reconcile / reset

app/streamlit_app.py
scripts/
  render_generated.py     # renders data/generated/images (both layouts, multi-line)
  compute_expected.py     # independent expected results from structured records
  check_report.py         # expected vs observed → reports/check-results.md
tests/
reports/check-results.md
```

## Pipeline

```
input folders  ─► ingest ─► extract (per document, cached) ─► normalize (+corrections) ─┐
reference data (POs, receipts) ───────────────────────────────────────────────┤
                                                                              ▼
                                  reconcile_batch (pure, whole batch, ingest_seq order)
                                                                              ▼
                                      notes (non-reconciled only, cached) ─► state/ ─► UI
```

- **Extraction** is the only expensive step and is cached. Everything after it is cheap and deterministic.
- **Reconciliation always runs over the whole batch**, because duplicate detection is cross-invoice and a
  correction (e.g. of `invoice_number`) can change another invoice's status.

## Intake and identity

- Documents are discovered by scanning `data/inputs/images/` and then `data/generated/images/`
  (PNG/JPEG). `file_id` = image filename stem; it must be unique across both folders.
- **Original vs duplicate is decided by processing (ingestion) order, not by order on disk.**
  When a document is processed for the first time, it gets `ingested_at` (UTC timestamp) and
  `ingest_seq` (next integer, persisted in its state file). Both are set once and never changed by later
  runs, corrections or re-extraction; only `cli reset` clears them.
- Within one batch, new documents are processed sequentially, inputs folder first, then filename order
  within a folder, so a fresh run is reproducible. Documents added later get later `ingest_seq` values.
- Duplicate detection orders by `ingest_seq` (the timestamp is for display; a sequence avoids ties when
  two files are processed within the same clock tick). `clean.png` and `duplicate.png` are byte-identical,
  so processing order is the only thing that distinguishes original from duplicate.

## Reference data

- Seed POs are flat (`sku`, `quantity`, `unit_cents` on the PO). The loader converts a flat PO into a PO with
  one line. Generated POs use `lines: [{sku, quantity, unit_cents}]`. Same for receipts.
- The app loads only `purchase_orders` and `receipts` from `data/inputs/seed.json` and
  `data/generated/reference.json`. Never the `invoices` array.
- Internal model: `PurchaseOrder{po_id, supplier_id, lines[PoLine{line_no, sku, quantity, unit_cents}], source}`,
  `Receipt{receipt_id, po_id, lines[{sku, quantity}], source}`. `source` = file path the record came from.

## Schemas

### Layer 1 — model output (`RawExtraction`, used as Gemini `response_schema`)

```python
class RawLine(BaseModel):
    sku: str | None
    description: str | None
    quantity: str | None      # exactly as printed
    unit_price: str | None    # e.g. "24.00"
    line_total: str | None

class RawExtraction(BaseModel):
    invoice_number: str | None
    supplier_id: str | None
    po_id: str | None
    currency: str | None      # e.g. "USD" from a "(USD)" label
    lines: list[RawLine]
    invoice_total: str | None
    warnings: list[str]       # placeholders, unreadable fields, oddities
```

All values are strings copied as printed. `null` when absent, unreadable or a placeholder such as
"(missing)". No confidence scores. Single-line seed invoices produce `lines` of length 1, with
`line_total` = the printed total.

### Layer 2 — normalized (`NormalizedInvoice`, produced in code)

```python
class NormalizedLine(BaseModel):
    line_no: int
    sku: str | None
    description: str | None
    quantity: int | None
    unit_cents: int | None
    line_total_cents: int | None
    errors: dict[str, str]

class NormalizedInvoice(BaseModel):
    invoice_number: str | None
    supplier_id: str | None
    po_id: str | None
    currency: str | None
    lines: list[NormalizedLine]
    invoice_total_cents: int | None
    errors: dict[str, str]      # field path -> reason
    flags: list[str]            # e.g. line_total_mismatch, invoice_total_mismatch
```

Normalization rules:
- Money: strip `$`, spaces, thousands separators → `Decimal` → must have ≤ 2 decimals → `int(d * 100)`.
  More decimals or unparsable → error, no rounding.
- Quantity: positive integer, else error.
- IDs and SKU: `strip()` only. No case changes or "fixing" (`PO 1` stays `PO 1`, `PO-S` stays `PO-S`).
- Currency: must be `USD` if present; otherwise error.
- Internal checks (flags, not errors): `quantity × unit_cents ≠ line_total_cents` → `line_total_mismatch`;
  `Σ line_total_cents ≠ invoice_total_cents` → `invoice_total_mismatch`.
- **Validity:** the extraction is `invalid` if `invoice_number` is null, `lines` is empty, any line field
  is null/unparsable, or `invoice_total` is null/unparsable. `supplier_id` and `po_id` may be null —
  that is a missing reference (→ `unresolved`), not invalid extraction.

Corrections are applied to the **raw string** values before normalization, so corrected values pass exactly
the same rules as model output.

### Layer 3 — saved state (`data/state/invoices/<file_id>.json`)

```json
{
  "file_id": "wrong-price",
  "image_path": "data/inputs/images/wrong-price.png",
  "ingest_seq": 2,
  "ingested_at": "ISO-8601 UTC",
  "extraction": {
    "status": "ok | failed",
    "source": "live | cached | simulated",
    "provider": "gemini", "model": "<GEMINI_MODEL>", "prompt_version": "extract-v1",
    "cache_key": "<sha256>", "error": null,
    "raw": { "...RawExtraction..." }
  },
  "corrections": [
    {"field": "lines[0].unit_price", "original": "24.00", "corrected": "20.00",
     "reason": "free text", "at": "ISO-8601 UTC"}
  ],
  "normalized": { "...NormalizedInvoice from raw + corrections..." },
  "reconciliation": { "...see below..." },
  "note": {"text": "...", "source": "live | cached", "guard_passed": true, "prompt_version": "note-v1"},
  "review": {"status": "pending | in_review | done", "comment": "", "updated_at": "..."}
}
```

Writes are atomic: write `<file>.tmp`, then `os.replace`. Batch summary in `data/state/summary.json`.

## Extraction providers, cache and replay

- `MODEL_MODE=live`: call Gemini, then write the response to the cache.
- `MODEL_MODE=replay`: read only from the cache. No key needed. A missing cache entry gives
  `extraction.status = failed` with a clear error; the batch continues.
- Cache key = `sha256(image_bytes + prompt_version + model)`. Cache file
  `data/model_cache/extract/<key>.json` holds metadata (provider, model, prompt_version, created_at,
  image sha256, file_id first seen) plus the raw response text and the parsed object.
  `clean` and `duplicate` share one cache entry because the images are identical. That is fine;
  duplicate detection uses extracted fields, never image hashes.
- Gemini settings: `temperature=0`, `response_mime_type="application/json"`,
  `response_schema=RawExtraction`, a fixed `max_output_tokens`. Record all of them in the README and manifest.
- Live calls: timeout and up to 2 retries with backoff on transient errors. Invalid JSON or schema failure →
  `failed` with the error text saved; no silent repair.
- **Simulations** (`data/simulations.json`): per-`file_id` entries that either replace the raw extraction
  (e.g. a misread `po_id`) or force a failure. Applied when `USE_SIMULATIONS=1` (default). The result is
  labelled `source=simulated`. The real cached response for the same image is kept and shown alongside.
- `SIMULATED_FAILURES=file_id,...` env var forces an API failure for listed documents, to demonstrate
  that the batch continues.

## Matching

1. Invoice has null `supplier_id` or `po_id` → `unresolved` (`missing_reference`).
2. No PO with that `po_id` → `unresolved` (`unknown_po`).
3. PO exists but `po.supplier_id ≠ invoice.supplier_id` → `unresolved` (`conflicting_reference`).
4. Lines: each invoice line matches the PO line with the same SKU. SKU not on the PO → line
   `sku_not_on_po`; SKU appearing more than once on the PO or on the invoice → line `ambiguous_sku`.
   Any unresolved line → invoice `unresolved`.
5. Receipt lines: matched by `(po_id, sku)`. Missing receipt data for a matched line → finding
   `no_receipt` (invoice `unresolved`, because the received quantity cannot be compared).

Every match records the source references used (`po_id` + line_no, `receipt_id`, source file).

## Reconciliation

Per matched line:
- `expected_line_cents = po_line.quantity × po_line.unit_cents` (ordered qty × agreed price — domain rule 3)
- `billed_line_cents = line_total_cents`
- `difference_cents = billed − expected`
- Findings: `price_diff` (unit ≠ agreed), `qty_over_ordered`, `qty_under_ordered`,
  `qty_over_received`, `short_receipt` (received < ordered), `line_total_mismatch`.

Per invoice:
- `expected_cents = Σ expected` over matched lines; `billed_cents = invoice_total_cents`;
  `difference_cents = billed − expected`.
- PO lines with no invoice line → finding `po_line_not_billed` (not added to expected).
- `invoice_total_mismatch` flag carried as a finding.

Status, first match wins:

1. `extraction_failed` — extraction status failed
2. `invalid` — normalization errors
3. `duplicate` — an earlier-processed (lower `ingest_seq`) valid invoice has the same `(supplier_id, invoice_number)`
4. `unresolved` — any matching problem; `expected_cents` and `difference_cents` are `null`
5. `discrepant` — any finding or non-zero difference
6. `reconciled` — matched, no findings, difference 0

Batch summary: counts per status; `recoverable_cents = Σ max(difference_cents, 0)` over `discrepant`
invoices only; `net_difference_cents` over `discrepant` only. Duplicates, unresolved, invalid and failed
never contribute. Duplicates carry `count_as_payable: false`.

## Notes and insight

- **Note** (`prompts/note-v1.md`): generated for `discrepant`, `unresolved` and `duplicate` invoices.
  Input is a compact JSON of verified findings with source references, never the image or raw extraction.
  Output: 3–6 sentences, neutral, starts with "DRAFT —", money written as `$X.XX`.
- **Number guard:** every `$X.XX` amount in the note must appear in the allowed set built from the
  findings. If not → `guard_passed=false`, shown as "needs review" in the UI. Notes are cached like
  extractions (key = findings hash + prompt version + model).
- **Insight:** deterministic aggregation (findings by type, supplier, SKU; recoverable by type) produces
  candidate observations. The model only words the strongest one (`prompts/insight-v1.md`). A plain
  deterministic fallback text is used if the model is unavailable.

## UI (Streamlit)

- **Queue:** status counts, recoverable total, status filter, table (file_id, invoice #, supplier, PO,
  status, difference, review status).
- **Invoice detail:** original image on the left; raw extraction vs effective (corrected) values on the right
  with provenance badge (live / cached / simulated); matched PO and receipt tables; line table of
  ordered / received / billed qty, agreed vs billed unit price, expected vs billed amount, difference;
  findings; draft note with guard status; correction form (field, new value, reason) → saves, reruns
  reconciliation for the batch, reloads; correction history; review status and comment.
- **Summary:** counts, recoverable total by finding type, insight text.
- The UI only reads and writes through `storage.py` / `pipeline.py`; no business logic in the UI.

## Configuration (`.env`)

```
GEMINI_API_KEY=
GEMINI_MODEL=
MODEL_MODE=replay        # live | replay
USE_SIMULATIONS=1
SIMULATED_FAILURES=      # comma-separated file_ids
```
