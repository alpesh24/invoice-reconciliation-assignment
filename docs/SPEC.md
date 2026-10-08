# Specification

Distilled from the assignment brief ("AI Invoice Reconciliation & Review Platform") and the starter pack.
Business rules are in `data/inputs/domain.md`; this file lists what the application must do.
Requirement IDs are referenced from `PLAN.md` and the README.

## Goal

Build a small accounts-payable review platform for a fictional business. Read supplier invoices, match them
to purchase orders and receipt records, explain differences between what was ordered, received and billed,
and give a reviewer the evidence plus a draft discrepancy note needed to resolve an exception.

Example: an invoice bills 5 units at 24.00; the matched PO agrees 20.00 per unit and the receipt confirms 5.
The platform calculates a difference of 20.00 (2,000 cents) and drafts a note citing the source records.

## Constraints

- One working day: max 8 hours total, including data preparation (30–60 min) and documentation.
- Local demo; lightweight app and simple file storage are enough.
- Core scope: 6–8 invoices, two layouts, simple PO and receipt records, one currency (USD), one review queue.
- Out of scope: tax, partial billing, FX, payment terms, accounting integrations, payment execution,
  authentication, cloud deployment.

## Requirements

### Data processing
- **R1** Load invoice documents and reference tables (POs, receipts), preserving source identifiers
  (`file_id`, `po_id`, `receipt_id`, line references).
- **R2** Use a document-capable model to extract the fields needed for matching and reconciliation, then
  validate the returned structure.
- **R3** Match invoices to local POs and receipts. Preserve the records used for each match. Leave missing or
  ambiguous references unresolved; never pick the closest-looking record.
- **R4** Calculate expected line amounts and totals in code, compare billed quantities with ordered and
  received quantities, identify duplicate invoices.
- **R5** Save extracted values, findings and review state.

### Analytics & insights
- **R6** Show reconciled, discrepant, duplicate and unresolved invoices with clear counts.
- **R7** Summarize supported price/quantity differences and their amounts. Duplicates and unresolved invoices
  are never part of the recoverable total.
- **R8** Use the model to draft a short discrepancy note from verified findings and source references.
- **R9** Explain one recurring issue or process improvement supported by the results, without treating a
  discrepancy as proof of wrongdoing.

### Dashboard
- **R10** Simple review queue with status filters.
- **R11** Invoice detail: original image beside extracted fields, matched PO and receipt records,
  expected-vs-billed calculations.
- **R12** Reviewer can correct an extracted value, rerun reconciliation and save review state. The original
  extraction stays visible so the correction can be understood.

### Technical
- **R13** One end-to-end flow: local documents → real model extraction → matching → checked calculations →
  saved results → presentation.
- **R14** Handle missing references, unreadable or invalid extraction, and model/API failures without stopping
  the batch. Unresolved evidence and failed processing are visible.
- **R15** Documented rounding rule and currency-safe arithmetic (integer cents, `Decimal` parsing).
- **R16** All notes are drafts.
- **R17** Working programmatic model integration, saved responses from real calls, and a way to replay them
  without an API key. Cached responses and simulated failures are labelled.

## Mandatory demonstration (results table / test report)

| ID | Check |
|---|---|
| **M1** | A clean invoice matches the intended PO and receipt, and its amounts agree with an independently checked calculation. |
| **M2** | The incorrect unit price produces the expected discrepancy amount, with links to the invoice and the agreed price. |
| **M3** | The duplicate is flagged and excluded from totals that would count it as another payable invoice. |
| **M4** | The missing PO reference stays unresolved; no invented match, no unsupported expected amount. |
| **M5** | Correcting an extracted field reruns reconciliation, updates the saved result, and is still visible after restarting the app. |

Failures that could not be fixed must be explained.

## Reference cases

Five reference cases covering M1–M5, with expected results verified by calculation or source inspection
**before** evaluating the app, and stored separately from model outputs. Seed expected results apply to the
original seeds; recompute if added data changes a total. See `DATASET.md`.

## Optional (only after M1–M5 pass)

- PDF invoices in addition to images.
- Export of the review queue and verified discrepancy calculations.
- Record of reviewer decisions and draft-note revisions.

## Submission checklist

- [ ] Git repository with solution, dependencies, small sample and replay files, no sensitive data.
- [ ] Dataset: supplied seeds and rules, additions, generation method, assumptions, five checked reference cases.
- [ ] README: setup and run, architecture, model configuration, data assumptions, time spent, known
      limitations, how to replay saved responses without an API key.
- [ ] Brief presentation (3–5 min recording, a few slides, or a written walkthrough).
- [ ] LLM usage note: tools and models, generated components, one representative instruction, one
      correction or verification step.
- [ ] `ai-workflow/manifest.json` and `ai-workflow/README.md` completed (renamed from templates), all
      exercise-specific configuration saved, unused categories marked `not-used`, redactions explained,
      `.env.example` with variable names only.
- [ ] Check results for M1–M5: expected vs observed, unresolved failures explained.

## Evaluation criteria (for orientation)

Functional thinking (apply supplied rules, handle missing information), technical execution (end-to-end flow,
readable code, validation, checks that catch errors), LLM use (working components, verified results, saved
and reproducible configuration, one correction), creativity (own choices within the time limit),
communication (decisions, limitations, runnable instructions). Extra infrastructure earns no credit.
