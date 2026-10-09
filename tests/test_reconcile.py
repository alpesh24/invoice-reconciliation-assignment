"""Unit tests for reference loading, matching outcomes, statuses, duplicates and recoverable totals.

Expected values are hand-calculated from domain.md (expected = ordered qty x agreed unit price).
"""

from invoice_recon.matching import match_invoice
from invoice_recon.models import BatchItem, NormalizedInvoice, NormalizedLine
from invoice_recon.normalize import normalize
from invoice_recon.models import RawExtraction, RawLine
from invoice_recon.reconcile import reconcile_batch, reconcile_invoice
from invoice_recon.reference import parse_reference

REF = {
    "purchase_orders": [
        {"po_id": "PO-1", "supplier_id": "S1", "sku": "CAB-1", "quantity": 5, "unit_cents": 2000},
        {"po_id": "PO-2", "supplier_id": "S1", "sku": "CAB-1", "quantity": 5, "unit_cents": 2000},
        {"po_id": "PO-M", "supplier_id": "S2", "lines": [
            {"sku": "A", "quantity": 2, "unit_cents": 1000},
            {"sku": "B", "quantity": 3, "unit_cents": 500},
        ]},
        {"po_id": "PO-D", "supplier_id": "S1", "lines": [
            {"sku": "A", "quantity": 1, "unit_cents": 100},
            {"sku": "A", "quantity": 1, "unit_cents": 100},
        ]},
        {"po_id": "PO-N", "supplier_id": "S1", "sku": "CAB-1", "quantity": 5, "unit_cents": 2000},
    ],
    "receipts": [
        {"receipt_id": "RC-1", "po_id": "PO-1", "sku": "CAB-1", "quantity": 5},
        {"receipt_id": "RC-2", "po_id": "PO-2", "sku": "CAB-1", "quantity": 5},
        {"receipt_id": "RC-M", "po_id": "PO-M", "lines": [{"sku": "A", "quantity": 2}, {"sku": "B", "quantity": 3}]},
        {"receipt_id": "RC-D", "po_id": "PO-D", "sku": "A", "quantity": 1},
    ],
    "invoices": [{"must": "never be read"}],
}
ORDERS, RECEIPTS = parse_reference(REF, "ref.json")


def inv(number="INV-1", supplier="S1", po="PO-1", lines=((  "CAB-1", 5, 2000, 10000),), total=None):
    nl = [NormalizedLine(line_no=i + 1, sku=s, quantity=q, unit_cents=u, line_total_cents=t)
          for i, (s, q, u, t) in enumerate(lines)]
    return NormalizedInvoice(
        invoice_number=number, supplier_id=supplier, po_id=po, lines=nl,
        invoice_total_cents=sum(x.line_total_cents for x in nl) if total is None else total,
    )


def codes(rec):
    return sorted(f.code for f in rec.findings)


def test_reference_flat_and_lines_formats():
    po1 = next(p for p in ORDERS if p.po_id == "PO-1")
    assert [(l.line_no, l.sku, l.quantity, l.unit_cents) for l in po1.lines] == [(1, "CAB-1", 5, 2000)]
    pom = next(p for p in ORDERS if p.po_id == "PO-M")
    assert len(pom.lines) == 2 and pom.source == "ref.json"
    rcm = next(r for r in RECEIPTS if r.receipt_id == "RC-M")
    assert [(l.sku, l.quantity) for l in rcm.lines] == [("A", 2), ("B", 3)]


def test_clean_reconciled():
    r = reconcile_invoice(inv(), ORDERS, RECEIPTS)
    assert (r.status, r.expected_cents, r.billed_cents, r.difference_cents) == ("reconciled", 10000, 10000, 0)
    assert r.lines[0].receipt_id == "RC-1" and r.po_source == "ref.json"


def test_worked_example_price_diff():
    r = reconcile_invoice(inv(number="INV-2", po="PO-2", lines=(("CAB-1", 5, 2400, 12000),)), ORDERS, RECEIPTS)
    assert (r.status, r.expected_cents, r.billed_cents, r.difference_cents) == ("discrepant", 10000, 12000, 2000)
    assert codes(r) == ["price_diff"]


def test_matching_outcomes():
    assert match_invoice(inv(po=None), ORDERS, RECEIPTS).problems == ["missing_reference"]
    assert match_invoice(inv(supplier=None), ORDERS, RECEIPTS).problems == ["missing_reference"]
    assert match_invoice(inv(po="PO-X"), ORDERS, RECEIPTS).problems == ["unknown_po"]
    assert match_invoice(inv(supplier="S2"), ORDERS, RECEIPTS).problems == ["conflicting_reference"]
    assert match_invoice(inv(po="PO-1 "), ORDERS, RECEIPTS).problems == ["unknown_po"]  # no fuzzy matching
    dup_orders = ORDERS + ORDERS[:1]
    assert match_invoice(inv(), dup_orders, RECEIPTS).problems == ["ambiguous_po"]


def test_amount_alone_does_not_match():
    # PO-1 and PO-2 are identical; without a PO id nothing is chosen.
    r = reconcile_invoice(inv(po=None), ORDERS, RECEIPTS)
    assert r.status == "unresolved" and r.expected_cents is None and r.difference_cents is None


def test_unresolved_line_problems():
    r = reconcile_invoice(inv(po="PO-M", supplier="S2", lines=(("A", 2, 1000, 2000), ("Z", 1, 5, 5))), ORDERS, RECEIPTS)
    assert r.status == "unresolved" and "sku_not_on_po" in codes(r) and r.expected_cents is None
    r = reconcile_invoice(inv(po="PO-D", lines=(("A", 1, 100, 100),)), ORDERS, RECEIPTS)
    assert r.status == "unresolved" and codes(r) == ["ambiguous_sku"]
    r = reconcile_invoice(inv(lines=(("CAB-1", 2, 2000, 4000), ("CAB-1", 3, 2000, 6000))), ORDERS, RECEIPTS)
    assert r.status == "unresolved" and "ambiguous_sku" in codes(r)


def test_no_receipt_unresolved():
    r = reconcile_invoice(inv(po="PO-N"), ORDERS, RECEIPTS)
    assert r.status == "unresolved" and codes(r) == ["no_receipt"] and r.difference_cents is None


def test_multi_line_reconciled():
    r = reconcile_invoice(inv(po="PO-M", supplier="S2", lines=(("A", 2, 1000, 2000), ("B", 3, 500, 1500))), ORDERS, RECEIPTS)
    assert (r.status, r.expected_cents, r.difference_cents) == ("reconciled", 3500, 0)


def test_qty_findings():
    over = reconcile_invoice(inv(lines=(("CAB-1", 6, 2000, 12000),)), ORDERS, RECEIPTS)
    assert over.status == "discrepant" and over.difference_cents == 2000
    assert codes(over) == ["qty_over_ordered", "qty_over_received"]
    under = reconcile_invoice(inv(lines=(("CAB-1", 4, 2000, 8000),)), ORDERS, RECEIPTS)
    assert under.difference_cents == -2000 and codes(under) == ["qty_under_ordered"]


def test_short_receipt_difference_can_be_zero():
    orders, receipts = parse_reference({
        "purchase_orders": [{"po_id": "P", "supplier_id": "S1", "sku": "X", "quantity": 5, "unit_cents": 100}],
        "receipts": [{"receipt_id": "R", "po_id": "P", "sku": "X", "quantity": 3}],
    })
    r = reconcile_invoice(inv(po="P", lines=(("X", 5, 100, 500),)), orders, receipts)
    assert r.status == "discrepant" and r.difference_cents == 0
    assert codes(r) == ["qty_over_received", "short_receipt"]


def test_total_mismatch_findings():
    r = reconcile_invoice(inv(lines=(("CAB-1", 5, 2000, 9000),)), ORDERS, RECEIPTS)
    assert r.status == "discrepant" and r.difference_cents == -1000 and "line_total_mismatch" in codes(r)
    n = normalize(RawExtraction(
        invoice_number="I", supplier_id="S1", po_id="PO-1", lines=[RawLine(sku="CAB-1", quantity="5", unit_price="20.00", line_total="100.00")],
        invoice_total="110.00"))
    r = reconcile_invoice(n, ORDERS, RECEIPTS)
    assert r.status == "discrepant" and r.billed_cents == 11000 and r.difference_cents == 1000
    assert codes(r) == ["invoice_total_mismatch"]


def test_po_line_not_billed():
    r = reconcile_invoice(inv(po="PO-M", supplier="S2", lines=(("A", 2, 1000, 2000),)), ORDERS, RECEIPTS)
    assert r.status == "discrepant" and r.expected_cents == 2000 and r.difference_cents == 0
    assert codes(r) == ["po_line_not_billed"]


def item(fid, seq, invoice, ok=True):
    return BatchItem(file_id=fid, ingest_seq=seq, extraction_ok=ok, normalized=invoice, extraction_error=None if ok else "boom")


def test_batch_statuses_precedence_and_duplicate_ordering():
    bad = normalize(RawExtraction(invoice_number=None))
    items = [
        item("dup", 3, inv()),                       # same key as "orig" but ingested later
        item("orig", 1, inv()),
        item("fail", 2, None, ok=False),
        item("invalid", 4, bad),
        item("wrong", 5, inv(number="INV-2", po="PO-2", lines=(("CAB-1", 5, 2400, 12000),))),
        item("miss", 6, inv(number="INV-3", po=None)),
        item("dup-discrepant", 7, inv(number="INV-2", po="PO-2", lines=(("CAB-1", 5, 2400, 12000),))),
    ]
    res, summary = reconcile_batch(items, ORDERS, RECEIPTS)
    assert res["orig"].status == "reconciled"
    assert res["dup"].status == "duplicate" and res["dup"].duplicate_of == "orig" and res["dup"].count_as_payable is False
    assert res["dup"].expected_cents is None and res["dup"].difference_cents is None
    assert res["fail"].status == "extraction_failed" and res["fail"].error == "boom"
    assert res["invalid"].status == "invalid" and "invoice_number" in res["invalid"].errors
    assert res["wrong"].status == "discrepant"
    assert res["dup-discrepant"].status == "duplicate"  # duplicate wins over discrepant
    assert res["miss"].status == "unresolved"
    assert summary.counts == {"extraction_failed": 1, "invalid": 1, "duplicate": 2,
                              "unresolved": 1, "discrepant": 1, "reconciled": 1}
    # recoverable: only the discrepant "wrong" invoice, 2000 cents
    assert summary.recoverable_cents == 2000 and summary.net_difference_cents == 2000


def test_duplicate_independent_of_list_order_and_suppliers():
    a = [item("a", 1, inv()), item("b", 2, inv())]
    r1, _ = reconcile_batch(a, ORDERS, RECEIPTS)
    r2, _ = reconcile_batch(list(reversed(a)), ORDERS, RECEIPTS)
    assert r1["b"].status == r2["b"].status == "duplicate" and r1["a"].status == r2["a"].status == "reconciled"
    # same number from a different supplier is not a duplicate
    r3, _ = reconcile_batch([item("a", 1, inv()), item("b", 2, inv(supplier="S2", po="PO-M", lines=(("A", 2, 1000, 2000), ("B", 3, 500, 1500))))], ORDERS, RECEIPTS)
    assert r3["b"].status == "reconciled"


def test_recoverable_excludes_undercharge_unresolved_duplicates():
    items = [
        item("over", 1, inv(number="I1", lines=(("CAB-1", 5, 2400, 12000),))),
        item("under", 2, inv(number="I2", po="PO-2", lines=(("CAB-1", 4, 2000, 8000),))),
        item("unres", 3, inv(number="I3", po="PO-X", lines=(("CAB-1", 5, 3000, 15000),))),
        item("dup", 4, inv(number="I1", lines=(("CAB-1", 5, 2400, 12000),))),
    ]
    res, s = reconcile_batch(items, ORDERS, RECEIPTS)
    assert res["under"].difference_cents == -2000
    assert s.recoverable_cents == 2000 and s.net_difference_cents == 0
