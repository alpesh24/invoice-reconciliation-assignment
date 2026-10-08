# Dataset extension plan

Used in Phase 6. Follow `.claude/skills/generate-assignment-data/SKILL.md` together with this file.
Seed files in `data/inputs/` stay unchanged; seed images are **not** re-rendered.
No randomness is used; all values below are hand-specified.

## Seed (unchanged)

| file_id | Invoice | PO | Lines | Layout | Expected |
|---|---|---|---|---|---|
| clean | INV-1 (S1) | PO-1 | CAB-1 5 × 20.00 | a | reconciled, expected 10000, billed 10000, diff 0 |
| wrong-price | INV-2 (S1) | PO-2 | CAB-1 5 × 24.00 | b | discrepant, expected 10000, billed 12000, diff +2000 |
| duplicate | INV-1 (S1) | PO-1 | same as clean | a | duplicate, count_as_payable false |
| missing-reference | INV-3 (S1) | (missing) | CAB-1 5 × 20.00 | b | unresolved, expected null, diff null |

PO-1 and PO-2 are identical in content (S1, CAB-1, 5 @ 2000), as are RC-1 and RC-2.

## New reference data (`data/generated/reference.json`, lines format)

| PO | Supplier | Lines | Receipt |
|---|---|---|---|
| PO-3 | S1 | CAB-1 × 10 @ 2000; ADP-2 × 4 @ 1500 | RC-3: CAB-1 10, ADP-2 4 |
| PO-4 | S2 | HUB-3 × 3 @ 4500; CAB-1 × 6 @ 1800 | RC-4: HUB-3 3, CAB-1 **4** |
| PO-5 | S1 | HUB-3 × 6 @ 4500; CAB-1 × 2 @ 2000 | RC-5: HUB-3 6, CAB-1 2 |

PO-4 prices CAB-1 at 1800 for supplier S2. This catches code that looks up prices by SKU globally
instead of from the matched PO.

## New invoices (`data/generated/invoice-records.json`)

### 5. `multi-line-price` — INV-10, S1, PO-3, layout a
Lines: CAB-1 10 × 20.00 = 200.00; ADP-2 4 × **17.50** = 70.00. Total 270.00.
Expected 26000, billed 27000, difference **+1000** (all on the ADP-2 line). Status `discrepant`.
Covers: discrepancy attributed to a specific line and PO line in a multi-line invoice.

### 6. `correction` — INV-12, S1, PO-5, layout b
Lines: HUB-3 6 × 45.00 = 270.00; CAB-1 2 × 20.00 = 40.00. Total 310.00. The image clearly shows `PO-5`.
**Simulated** extraction error in `data/simulations.json`: `po_id` read as `PO-S` (5↔S confusion),
all other fields correct. Labelled `source=simulated`; the real cached response is also kept.
- Before correction: `PO-S` not found → `unresolved`, expected null, difference null.
- Correction: `po_id` `PO-S` → `PO-5`.
- After correction: `reconciled`, expected 31000, billed 31000, difference 0.

Covers: M5 (correction → rerun → saved → survives restart) and "no fuzzy match to the closest PO".

### 7. `conflicting-supplier` — INV-30, S2, PO-1, layout a
Line: CAB-1 5 × 20.00 = 100.00. Total 100.00.
PO-1 belongs to S1 → `unresolved` (`conflicting_reference`), expected null, difference null.
Amounts are identical to PO-1, so amount-based matching would wrongly accept it.

### 8. `short-receipt` — INV-40, S2, PO-4, layout b
Lines: HUB-3 3 × 45.00 = 135.00; CAB-1 6 × 18.00 = 108.00. Total 243.00.
Billed = ordered for both lines; RC-4 confirms only 4 of CAB-1.
Expected 24300, billed 24300, difference 0, CAB-1 line finding `short_receipt`. Status `discrepant`,
contributes 0 to recoverable. Ambiguity A1: no amount is invented for the shortfall.

## Expected batch summary

| Status | Before correction | After correction |
|---|---|---|
| reconciled | 1 (clean) | 2 (+ correction) |
| discrepant | 3 (wrong-price, multi-line-price, short-receipt) | 3 |
| duplicate | 1 | 1 |
| unresolved | 3 (missing-reference, conflicting-supplier, correction) | 2 |

Recoverable total: 2000 + 1000 + 0 = **3000 cents** in both states.

## Five reference cases

| Check | Case |
|---|---|
| M1 | clean |
| M2 | wrong-price |
| M3 | duplicate |
| M4 | missing-reference |
| M5 | correction |

The other three new invoices are additional test cases in the same report.
All expected values are computed by `scripts/compute_expected.py` (no import from `src/`) and inspected by
the user before the application is evaluated.

## Rendering

`scripts/render_generated.py` extends the logic of `data/inputs/render_invoices.py` to multiple lines,
keeping both layouts recognizable:
- Layout a: header band, vertical header fields, then a line table (SKU, Qty, Unit price, Line total), total.
- Layout b: header band, two-column header fields, then line rows, total.
Outputs go to `data/generated/images/`. Document the method and the mapping from the template fields to
the lines format in `data/generated/GENERATION.md`.
