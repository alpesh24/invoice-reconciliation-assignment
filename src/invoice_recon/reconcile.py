"""Findings, amounts, statuses and batch totals. Pure and deterministic; no model involved."""

from .matching import match_invoice
from .models import (
    STATUSES,
    BatchItem,
    BatchSummary,
    Finding,
    LineResult,
    NormalizedInvoice,
    PurchaseOrder,
    Receipt,
    Reconciliation,
)


def reconcile_invoice(
    invoice: NormalizedInvoice, orders: list[PurchaseOrder], receipts: list[Receipt]
) -> Reconciliation:
    """Reconcile one valid invoice (not a duplicate) against reference data."""
    match = match_invoice(invoice, orders, receipts)
    findings: list[Finding] = [Finding(code=code) for code in match.problems]
    line_results: list[LineResult] = []
    discrepancy_findings: list[Finding] = []
    expected_total = 0

    for ln, lm in zip(invoice.lines, match.lines):
        pl = lm.po_line
        res = LineResult(
            line_no=ln.line_no,
            sku=ln.sku,
            billed_qty=ln.quantity,
            billed_unit_cents=ln.unit_cents,
            billed_cents=ln.line_total_cents,
            problems=list(lm.problems),
        )
        findings += [Finding(code=code, line_no=ln.line_no) for code in lm.problems]
        if pl is not None:
            res.po_line_no = pl.line_no
            res.ordered_qty = pl.quantity
            res.agreed_unit_cents = pl.unit_cents
            res.receipt_id = lm.receipt_id
            res.received_qty = lm.received_qty
            res.expected_cents = pl.quantity * pl.unit_cents
            res.difference_cents = ln.line_total_cents - res.expected_cents
            expected_total += res.expected_cents

            def add(code: str, **detail: int) -> None:
                discrepancy_findings.append(Finding(code=code, line_no=ln.line_no, detail=detail))

            if ln.unit_cents != pl.unit_cents:
                add("price_diff", billed_unit_cents=ln.unit_cents, agreed_unit_cents=pl.unit_cents)
            if ln.quantity > pl.quantity:
                add("qty_over_ordered", billed_qty=ln.quantity, ordered_qty=pl.quantity)
            elif ln.quantity < pl.quantity:
                add("qty_under_ordered", billed_qty=ln.quantity, ordered_qty=pl.quantity)
            if lm.received_qty is not None:
                if ln.quantity > lm.received_qty:
                    add("qty_over_received", billed_qty=ln.quantity, received_qty=lm.received_qty)
                if lm.received_qty < pl.quantity:
                    add("short_receipt", received_qty=lm.received_qty, ordered_qty=pl.quantity)
            if ln.quantity * ln.unit_cents != ln.line_total_cents:
                add(
                    "line_total_mismatch",
                    quantity=ln.quantity,
                    unit_cents=ln.unit_cents,
                    line_total_cents=ln.line_total_cents,
                )
        line_results.append(res)

    base = dict(
        billed_cents=invoice.invoice_total_cents,
        po_id=match.po.po_id if match.po else None,
        po_source=match.po.source if match.po else None,
        lines=line_results,
    )
    if not match.resolved:
        return Reconciliation(status="unresolved", findings=findings, **base)

    billed_skus = {ln.sku for ln in invoice.lines}
    for pl in match.po.lines:
        if pl.sku not in billed_skus:
            discrepancy_findings.append(
                Finding(
                    code="po_line_not_billed",
                    detail={"po_line_no": pl.line_no, "sku": pl.sku, "ordered_qty": pl.quantity},
                )
            )
    if "invoice_total_mismatch" in invoice.flags:
        discrepancy_findings.append(
            Finding(
                code="invoice_total_mismatch",
                detail={
                    "lines_total_cents": sum(ln.line_total_cents for ln in invoice.lines),
                    "invoice_total_cents": invoice.invoice_total_cents,
                },
            )
        )

    difference = invoice.invoice_total_cents - expected_total
    status = "discrepant" if (discrepancy_findings or difference != 0) else "reconciled"
    return Reconciliation(
        status=status,
        expected_cents=expected_total,
        difference_cents=difference,
        findings=discrepancy_findings,
        **base,
    )


def _is_valid(item: BatchItem) -> bool:
    return item.extraction_ok and item.normalized is not None and not item.normalized.errors


def reconcile_batch(
    items: list[BatchItem], orders: list[PurchaseOrder], receipts: list[Receipt]
) -> tuple[dict[str, Reconciliation], BatchSummary]:
    """Reconcile the whole batch in ingest_seq order; duplicates are detected across invoices."""
    results: dict[str, Reconciliation] = {}
    originals: dict[tuple[str, str], str] = {}  # (supplier_id, invoice_number) -> file_id of first valid

    for item in sorted(items, key=lambda i: i.ingest_seq):
        if not item.extraction_ok:
            results[item.file_id] = Reconciliation(
                status="extraction_failed", error=item.extraction_error or "extraction failed", count_as_payable=False
            )
            continue
        inv = item.normalized
        if inv is None or inv.errors:
            results[item.file_id] = Reconciliation(
                status="invalid",
                errors=dict(inv.errors) if inv else {"normalized": "no normalized invoice is available for this extraction"},
                billed_cents=None,
                count_as_payable=False,
            )
            continue
        if inv.supplier_id is not None:
            key = (inv.supplier_id, inv.invoice_number)
            if key in originals:
                results[item.file_id] = Reconciliation(
                    status="duplicate",
                    billed_cents=inv.invoice_total_cents,
                    duplicate_of=originals[key],
                    count_as_payable=False,
                    findings=[Finding(code="duplicate_invoice", detail={"original": originals[key]})],
                )
                continue
            originals[key] = item.file_id
        results[item.file_id] = reconcile_invoice(inv, orders, receipts)

    counts = {status: 0 for status in STATUSES}
    recoverable = 0
    net = 0
    for res in results.values():
        counts[res.status] += 1
        if res.status == "discrepant":
            recoverable += max(res.difference_cents, 0)
            net += res.difference_cents
    return results, BatchSummary(counts=counts, recoverable_cents=recoverable, net_difference_cents=net)
