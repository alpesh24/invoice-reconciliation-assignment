"""Pure view-models for the review UI: rows, filters, labels, comparison tables. No I/O, no business rules.

Every number shown here was computed earlier by reconcile/normalize; this module only selects and formats.
"""

from invoice_recon.models import Finding, PurchaseOrder, RawExtraction, Receipt
from invoice_recon.money import format_cents
from invoice_recon.normalize import apply_corrections
from invoice_recon.storage import InvoiceState

PROVENANCE_LABELS = {
    "live": "LIVE model response",
    "cached": "CACHED model response (saved earlier live call)",
    "simulated": "SIMULATED (not a real model response)",
}

FINDING_LABELS = {
    "price_diff": "Billed unit price differs from the agreed PO price",
    "qty_over_ordered": "Billed quantity is above the ordered quantity",
    "qty_under_ordered": "Billed quantity is below the ordered quantity",
    "qty_over_received": "Billed quantity is above the received quantity",
    "short_receipt": "Received quantity is below the ordered quantity",
    "line_total_mismatch": "Line total differs from quantity x unit price",
    "invoice_total_mismatch": "Invoice total differs from the sum of line totals",
    "po_line_not_billed": "PO line has no invoice line",
    "duplicate_invoice": "Same supplier and invoice number as an earlier invoice",
    "missing_reference": "Supplier or PO reference is missing",
    "unknown_po": "No purchase order with this PO id",
    "conflicting_reference": "PO belongs to a different supplier",
    "sku_not_on_po": "SKU is not on the purchase order",
    "ambiguous_sku": "SKU appears more than once, so it cannot be matched",
    "no_receipt": "No receipt data for this line",
}

_CENTS_KEYS_SUFFIX = "_cents"
_TOP_FIELDS = ("invoice_number", "supplier_id", "po_id", "currency", "invoice_total")
_LINE_FIELDS = ("sku", "description", "quantity", "unit_price", "line_total")


def money_or_dash(cents: int | None) -> str:
    return "-" if cents is None else format_cents(cents)


def provenance_label(source: str | None) -> str:
    return PROVENANCE_LABELS.get(source or "", "no model response")


def queue_row(state: InvoiceState) -> dict[str, str | int]:
    """One queue table row. Identifiers come from the effective (corrected) normalized values."""
    inv = state.normalized
    rec = state.reconciliation
    return {
        "file_id": state.file_id,
        "ingest_seq": state.ingest_seq,
        "invoice_number": (inv.invoice_number if inv else None) or "-",
        "supplier_id": (inv.supplier_id if inv else None) or "-",
        "po_id": (inv.po_id if inv else None) or "-",
        "status": rec.status if rec else "not_reconciled",
        "difference": money_or_dash(rec.difference_cents) if rec else "-",
        "review": state.review.status,
        "source": state.extraction.source or "-",
        "corrected": "yes" if state.corrections else "",
    }


def queue_rows(states: dict[str, InvoiceState]) -> list[dict[str, str | int]]:
    return [queue_row(s) for s in sorted(states.values(), key=lambda s: s.ingest_seq)]


def filter_rows(
    rows: list[dict[str, str | int]], statuses: list[str] | None = None, review: list[str] | None = None
) -> list[dict[str, str | int]]:
    """Keep rows whose status / review status is in the given lists (None or empty = no filter)."""
    out = rows
    if statuses:
        out = [r for r in out if r["status"] in statuses]
    if review:
        out = [r for r in out if r["review"] in review]
    return out


def raw_comparison_rows(original: RawExtraction, state: InvoiceState) -> list[dict[str, str]]:
    """Original raw string vs effective raw string (original + correction overlay) for every field."""
    effective = apply_corrections(original, state.corrections)
    rows: list[dict[str, str]] = []

    def add(name: str, before: str | None, after: str | None) -> None:
        rows.append(
            {
                "field": name,
                "original": before if before is not None else "(null)",
                "effective": after if after is not None else "(null)",
                "changed": "corrected" if before != after else "",
            }
        )

    for f in _TOP_FIELDS:
        add(f, getattr(original, f), getattr(effective, f))
    for i, (a, b) in enumerate(zip(original.lines, effective.lines)):
        for f in _LINE_FIELDS:
            add(f"lines[{i}].{f}", getattr(a, f), getattr(b, f))
    return rows


def correctable_fields(raw: RawExtraction) -> list[str]:
    """Field names a reviewer may correct (those that `get_raw_value` accepts)."""
    names = list(_TOP_FIELDS)
    for i in range(len(raw.lines)):
        names += [f"lines[{i}].{f}" for f in _LINE_FIELDS]
    return names


def line_table_rows(state: InvoiceState) -> list[dict[str, str]]:
    rec = state.reconciliation
    if rec is None:
        return []
    return [
        {
            "line": str(ln.line_no),
            "sku": ln.sku or "-",
            "ordered qty": "-" if ln.ordered_qty is None else str(ln.ordered_qty),
            "received qty": "-" if ln.received_qty is None else str(ln.received_qty),
            "billed qty": "-" if ln.billed_qty is None else str(ln.billed_qty),
            "agreed unit": money_or_dash(ln.agreed_unit_cents),
            "billed unit": money_or_dash(ln.billed_unit_cents),
            "expected": money_or_dash(ln.expected_cents),
            "billed": money_or_dash(ln.billed_cents),
            "difference": money_or_dash(ln.difference_cents),
            "problems": ", ".join(ln.problems),
        }
        for ln in rec.lines
    ]


def format_detail_value(key: str, value: int | str | None) -> str:
    if value is None:
        return "-"
    if key.endswith(_CENTS_KEYS_SUFFIX) and isinstance(value, int):
        return format_cents(value)
    return str(value)


def finding_row(f: Finding) -> dict[str, str]:
    return {
        "finding": f.code,
        "meaning": FINDING_LABELS.get(f.code, f.code),
        "line": "" if f.line_no is None else str(f.line_no),
        "detail": ", ".join(f"{k}={format_detail_value(k, v)}" for k, v in f.detail.items()),
    }


def finding_rows(state: InvoiceState) -> list[dict[str, str]]:
    return [finding_row(f) for f in state.reconciliation.findings] if state.reconciliation else []


def matched_po(state: InvoiceState, orders: list[PurchaseOrder]) -> PurchaseOrder | None:
    """The PO the reconciliation recorded, looked up by exact (supplier_id, po_id) and source file."""
    rec, inv = state.reconciliation, state.normalized
    if rec is None or inv is None or rec.po_id is None:
        return None
    for po in orders:
        if po.po_id == rec.po_id and po.supplier_id == inv.supplier_id and (rec.po_source in (None, po.source)):
            return po
    return None


def po_rows(po: PurchaseOrder) -> list[dict[str, str]]:
    return [
        {"line": str(ln.line_no), "sku": ln.sku, "quantity": str(ln.quantity), "unit price": format_cents(ln.unit_cents)}
        for ln in po.lines
    ]


def receipt_rows(po_id: str, receipts: list[Receipt]) -> list[dict[str, str]]:
    return [
        {"receipt": rc.receipt_id, "sku": ln.sku, "quantity": str(ln.quantity)}
        for rc in receipts
        if rc.po_id == po_id
        for ln in rc.lines
    ]


def summary_finding_counts(states: dict[str, InvoiceState]) -> dict[str, int]:
    """Number of findings per code over all invoices (counts only; no amounts are attributed to a code)."""
    counts: dict[str, int] = {}
    for s in states.values():
        for f in (s.reconciliation.findings if s.reconciliation else []):
            counts[f.code] = counts.get(f.code, 0) + 1
    return dict(sorted(counts.items()))


def correction_history_rows(state: InvoiceState) -> list[dict[str, str]]:
    return [
        {
            "at": c.at,
            "field": c.field,
            "original": c.original if c.original is not None else "(null)",
            "corrected": c.corrected if c.corrected is not None else "(null)",
            "reason": c.reason,
        }
        for c in state.corrections
    ]
