# Generated dataset (Phase 6)

All data is fictional. Nothing is random: every value is hand-specified in `docs/DATASET.md`, so no seed is
needed. Files in `data/inputs/` are unchanged and the seed images were not re-rendered.
These fixtures do not establish real-world model accuracy; they only exercise the application's rules.

## Files

| File | Purpose |
|---|---|
| `data/generated/reference.json` | New purchase orders PO-3..PO-5 and receipts RC-3..RC-5 (lines format) |
| `data/generated/invoice-records.json` | Structured records of the four new invoices (answer-key side; the application never reads it) |
| `scripts/render_generated.py` | Renders the records to `data/generated/images/*.png` (Pillow) |
| `data/generated/images/` | `multi-line-price`, `correction`, `conflicting-supplier`, `short-receipt` |
| `data/simulations.json` | Simulated misread for `correction` (`po_id` read as `PO-S`) |
| `data/expected/expected-results.json` | Expected results, computed by `scripts/compute_expected.py` |

## Method

1. Reference data was written by hand. PO-4 prices CAB-1 at 1800 for supplier S2 (seed PO-1/PO-2 use 2000 for
   S1), so code that looks prices up by SKU globally gives a wrong answer.
2. Invoice records follow `data/inputs/invoice.template.json`, extended from one `sku/quantity/unit_cents`
   to a `lines` array. Mapping: `sku`, `quantity`, `unit_cents` move into each line; a per-line
   `line_total_cents` is added; `total_cents` (printed invoice total), `layout`, `file_id`, `invoice_number`,
   `supplier_id`, `po_id` stay at invoice level.
3. `python scripts/render_generated.py` draws each record with the seed canvas (950x650), fonts and header
   colours. Layout a: green header band, vertical Supplier / Purchase order fields, a line table (SKU, Qty,
   Unit price, Line total), total. Layout b: blue header band, two-column Supplier / Purchase order, the same
   table, total at the right. The images print no description, like the seed images.
4. `python scripts/compute_expected.py` applies domain rules 1-4 (and DECISIONS A1, A4, A6, C4, C7) to the
   structured records with its own code and no import from `src/`. It asserts that its seed results equal
   `data/inputs/expected-seed-results.json`. Each result carries the rule that determines it.
   `price_differs` in `line_findings` is an informational label in the expected file only.

## Cases

| file_id | Invoice | Supplier / PO | Expected |
|---|---|---|---|
| multi-line-price | INV-10 | S1 / PO-3 | discrepant; expected 26000, billed 27000, difference +1000, all on ADP-2 |
| correction | INV-12 | S1 / PO-5 | Before: simulated `PO-S` gives unresolved (PO not found), expected null. Correction `po_id` `PO-S` to `PO-5`. After: reconciled, 31000 / 31000 / 0 |
| conflicting-supplier | INV-30 | S2 / PO-1 | unresolved (PO-1 belongs to S1), expected null; amounts equal PO-1 so amount matching would accept it |
| short-receipt | INV-40 | S2 / PO-4 | discrepant; 24300 / 24300 / 0; CAB-1 `short_receipt` (billed 6, received 4); no shortfall amount invented (A1) |

Batch totals (seed + new): before correction reconciled 1, discrepant 3, duplicate 1, unresolved 3; after
correction reconciled 2, discrepant 3, duplicate 1, unresolved 2; recoverable 3000 cents in both states.

## Deliberate special cases (not data errors)

- `correction`: the image is correct (`PO-5`); the wrong `PO-S` exists only in `data/simulations.json` and is
  labelled `simulated`.
- `conflicting-supplier`: deliberately references a PO of another supplier.
- `short-receipt`: billed equals ordered while less was received.

## Unresolved ambiguity

No new ambiguity. Short receipt follows A1; conflicting reference follows A4. Model extraction for the new
images is not yet cached; replay shows them as extraction failed until the live extraction step is approved
and run.
