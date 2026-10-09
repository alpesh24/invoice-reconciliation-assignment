"""Exact matching of an invoice to a PO, its lines to PO lines, and to receipts. Pure; no fuzzy logic."""

from collections import Counter

from pydantic import BaseModel, Field

from .models import NormalizedInvoice, PoLine, PurchaseOrder, Receipt


class LineMatch(BaseModel):
    line_no: int
    po_line: PoLine | None = None
    receipt_id: str | None = None
    received_qty: int | None = None
    problems: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    po: PurchaseOrder | None = None
    problems: list[str] = Field(default_factory=list)  # invoice-level reference problems
    lines: list[LineMatch] = Field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return not self.problems and all(not lm.problems for lm in self.lines)


def match_invoice(
    invoice: NormalizedInvoice, orders: list[PurchaseOrder], receipts: list[Receipt]
) -> MatchResult:
    """Match by exact (supplier_id, po_id), then lines by exact SKU within that PO."""
    if invoice.supplier_id is None or invoice.po_id is None:
        return MatchResult(problems=["missing_reference"])

    same_po_id = [p for p in orders if p.po_id == invoice.po_id]
    if not same_po_id:
        return MatchResult(problems=["unknown_po"])
    exact = [p for p in same_po_id if p.supplier_id == invoice.supplier_id]
    if not exact:
        return MatchResult(problems=["conflicting_reference"])
    if len(exact) > 1:
        return MatchResult(problems=["ambiguous_po"])
    po = exact[0]

    invoice_skus = Counter(ln.sku for ln in invoice.lines)
    po_skus = Counter(pl.sku for pl in po.lines)
    receipt_entries: dict[str, list[tuple[str, int]]] = {}
    for rc in receipts:
        if rc.po_id == po.po_id:
            for rl in rc.lines:
                receipt_entries.setdefault(rl.sku, []).append((rc.receipt_id, rl.quantity))

    matches = []
    for ln in invoice.lines:
        lm = LineMatch(line_no=ln.line_no)
        if invoice_skus[ln.sku] > 1 or po_skus[ln.sku] > 1:
            lm.problems.append("ambiguous_sku")
        elif po_skus[ln.sku] == 0:
            lm.problems.append("sku_not_on_po")
        else:
            lm.po_line = next(pl for pl in po.lines if pl.sku == ln.sku)
            entries = receipt_entries.get(ln.sku, [])
            if not entries:
                lm.problems.append("no_receipt")
            elif len(entries) > 1:
                lm.problems.append("ambiguous_receipt")
            else:
                lm.receipt_id, lm.received_qty = entries[0]
        matches.append(lm)
    return MatchResult(po=po, lines=matches)
