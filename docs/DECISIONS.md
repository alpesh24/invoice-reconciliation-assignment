# Decisions and ambiguities

Decisions made before implementation. Do not re-decide them without asking. The ambiguity list feeds the
README section "Unresolved ambiguity", which `domain.md` asks for.

## Stack and setup

| ID | Decision | Reason |
|---|---|---|
| D1 | Python 3.11+, pip + `requirements.txt`, venv | Simple to reproduce for a reviewer |
| D2 | Streamlit UI | Fastest way to an image-beside-fields review screen in Python; the UI is a thin layer over the package |
| D3 | JSON files on disk, atomic writes, no database | Small volume; reviewer can open files and read git diffs |
| D4 | Gemini API (free tier) via `google-genai`; model ID in `.env` | No model access was provided by the hiring team; free tier covers the volume; data is fictional |
| D5 | Replay mode as default (`MODEL_MODE=replay`), cache committed | Brief requires replay without an API key; makes results and tests reproducible |
| D6 | Claude Code setup: default settings, no hooks, no MCP; two project subagents (`implementer`, `reviewer` in `.claude/agents/`) are used by the implement-test-review loop | Subagents give an independent read-only review; hooks and MCP were not needed and are marked `not-used` in the manifest. Corrected in Phase 8 (earlier text said "no subagents"; snapshot `ai-workflow/snapshots/DECISIONS.md.phase-8.md`) |
| D7 | English for code, UI, docs and notes | Submission language |
| D8 | Starter files moved unchanged to `data/inputs/`, treated as read-only | Clear separation of supplied vs generated data |
| D9 | `.claude/skills/verify-reconciliation/SKILL.md` is kept unchanged and listed as `not-used` | It refers to `scripts/eval.py`, a 98% accuracy gate and ruff/mypy, which do not exist in this project; the loop never used it (user decision, Phase 8, Q-P8-2) |
| D10 | Claude Code version 2.1.295; orchestrator model Sonnet 5.5 (`claude-sonnet-5-5`); recorded in `ai-workflow/README.md` and `manifest.json` | User-supplied facts (Phase 8, Q-P8-3). Phase 2 and 5 durations stay "not recorded" in PROGRESS.md and the README |

## Extraction

| ID | Decision | Reason |
|---|---|---|
| E1 | Model returns strings exactly as printed; code converts to cents | Model must not do arithmetic; one place for currency rules |
| E2 | `null` + warning for absent, unreadable or placeholder fields; never inferred | Required for the missing-reference case |
| E3 | No model confidence field | Self-reported confidence is not calibrated and would mislead the reviewer |
| E4 | Multi-line invoices supported (`lines` array); one PO per invoice | Generality at modest cost; domain matches per invoice by PO-ID |
| E5 | IDs only trimmed, never "fixed" | Fixing (e.g. `PO-S` → `PO-5`) would be fuzzy matching in disguise |
| E6 | Missing `supplier_id` / `po_id` → `unresolved`, not `invalid` | Domain rule 2: missing reference remains unresolved |
| E7 | Prompts versioned by filename; version is part of the cache key | Traceable AI configuration; prompt changes invalidate cache |

## Reconciliation

| ID | Decision | Reason |
|---|---|---|
| C1 | Integer cents; `Decimal` parsing; > 2 decimals is an error; never round | Rounding rule: rounding is never needed because expected = integer × integer |
| C2 | Expected = **ordered** qty × agreed unit price (per PO line) | Domain rule 3 |
| C3 | Billed line = printed line total; billed invoice = printed invoice total | What the supplier billed; internal mismatches are flagged, not silently recomputed |
| C4 | Status precedence: extraction_failed → invalid → duplicate → unresolved → discrepant → reconciled | One deterministic status per invoice |
| C5 | Duplicate = same `(supplier_id, invoice_number)` as an earlier-processed valid invoice; the first processed is the original. Processing order = `ingest_seq` assigned once at first processing and persisted | Domain rule 4; the two seed images are byte-identical, so order must be explicit and must not depend on order on disk |
| C6 | Any unresolved line makes the whole invoice `unresolved`; no `partially_resolved` status | Avoids a partially supported recoverable amount; no new statuses beyond the brief |
| C7 | `recoverable_cents` = sum of positive differences of `discrepant` invoices only | Domain rule 4: positive = overcharge; duplicates/unresolved excluded |
| C8 | Reconciliation recomputes the whole batch after any correction | Dedupe is cross-invoice |
| C9 | Original extraction immutable; corrections are an overlay passing the same normalization | Brief: keep original visible; consistent validation |
| C10 | Model drafts notes only from verified findings JSON; number guard checks amounts | Notes must cite verified data only |

## Ambiguities in the supplied rules (to report in README)

| ID | Ambiguity | How we handle it |
|---|---|---|
| A1 | Received < ordered (short receipt) while billed = ordered: rules define the amount only against ordered qty | Line gets `short_receipt` finding, invoice `discrepant`, difference stays as calculated (may be 0). No amount is invented for the shortfall. |
| A2 | Billed qty ≠ ordered qty: classification beyond the difference amount is not specified | Findings `qty_over_ordered` / `qty_under_ordered`; amount per C2/C3 |
| A3 | Printed qty × unit ≠ printed line total, or Σ lines ≠ printed total | Billed = printed totals (C3); `line_total_mismatch` / `invoice_total_mismatch` findings → `discrepant` |
| A4 | "Conflicting reference" is not defined | PO exists but belongs to another supplier, or PO-ID not found → `unresolved` |
| A5 | Which of two identical invoices is the original | The one processed first (`ingest_seq`, C5) |
| A6 | An invoice that is both a duplicate and discrepant | `duplicate` wins (C4); its difference is not counted |
| A7 | A PO line that is not billed (partial billing is excluded from scope) | Finding `po_line_not_billed`, invoice `discrepant`, not added to expected |
| A8 | Matched PO line without receipt data | Finding `no_receipt`, invoice `unresolved` (received qty cannot be compared, as rule 3 requires) |
| A9 | Negative difference (undercharge) | Shown as a difference; not part of `recoverable_cents` |
| A10 | Same SKU twice on a PO or invoice | `ambiguous_sku` → `unresolved`; no line selection |
| A11 | Several receipt entries for the same `(po_id, sku)`, or two POs with the same `po_id` and supplier | `ambiguous_receipt` / `ambiguous_po` → `unresolved`; receipts are never summed (user-confirmed, Phase 1) |
| A12 | Missing/null invoice line `description` | Allowed; description is optional and does not affect validity. Supersedes the earlier Phase 1 decision "null description = invalid" (user decision, Phase 3, Q1 option a: the seed images print no description) |
| A13 | `supplier_id` null | `missing_reference` → `unresolved`; never a duplicate, since the duplicate key needs the supplier (user-confirmed, Phase 1) |
| A14 | `count_as_payable` is false only for duplicates; unresolved invoices keep it true | No rule in `domain.md` or the requirements makes unresolved invoices non-payable; ARCHITECTURE says only duplicates carry `false`. Unresolved invoices still never contribute to totals. Resolves Q-P7-1 (user decision, 2026-10-09). `scripts/compute_expected.py` aligned. |
| A15 | Keep the `qty_over_received` finding (billed qty > received qty) in the expected results | Domain rule 3 compares billed qty with both ordered and received qty (user-approved, 2026-10-09) |

## Open questions

_Add new questions here during implementation instead of deciding silently._

_None._
