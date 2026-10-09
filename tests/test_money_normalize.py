"""Unit tests for money parsing and normalization rules (values from domain.md / ARCHITECTURE rules)."""

import pytest

from invoice_recon.models import Correction, RawExtraction, RawLine
from invoice_recon.money import MoneyError, format_cents, parse_money, parse_quantity
from invoice_recon.normalize import apply_corrections, effective_normalized, normalize


@pytest.mark.parametrize(
    "text,cents",
    [("24.00", 2400), ("1,234.50", 123450), ("$24.00", 2400), ("24", 2400), ("24.5", 2450), ("0.00", 0), (" $ 100.00 ", 10000)],
)
def test_parse_money_ok(text, cents):
    assert parse_money(text) == cents
    assert isinstance(parse_money(text), int)


@pytest.mark.parametrize("text", ["24.005", "24.000", "abc", "", "-5.00", "1,23.00", "24.", None, "(missing)"])
def test_parse_money_errors(text):
    with pytest.raises(MoneyError):
        parse_money(text)


def test_parse_quantity():
    assert parse_quantity("5") == 5
    for bad in ("0", "-1", "2.5", "five", None, ""):
        with pytest.raises(MoneyError):
            parse_quantity(bad)


def test_format_cents():
    assert format_cents(12000) == "$120.00"
    assert format_cents(5) == "$0.05"
    assert format_cents(123450) == "$1,234.50"


def raw(**over):
    base = dict(
        invoice_number="INV-1",
        supplier_id="S1",
        po_id="PO-1",
        currency="USD",
        lines=[RawLine(description="Item", sku="CAB-1", quantity="5", unit_price="20.00", line_total="100.00")],
        invoice_total="100.00",
    )
    base.update(over)
    return RawExtraction(**base)


def test_normalize_valid():
    n = normalize(raw())
    assert not n.errors and not n.flags
    assert n.lines[0].quantity == 5 and n.lines[0].unit_cents == 2000
    assert n.lines[0].line_total_cents == 10000 and n.invoice_total_cents == 10000


def test_missing_references_are_not_errors():
    n = normalize(raw(po_id=None, supplier_id=None))
    assert n.errors == {} and n.po_id is None and n.supplier_id is None


def test_ids_only_trimmed():
    n = normalize(raw(po_id="  PO-S ", supplier_id="s1"))
    assert n.po_id == "PO-S" and n.supplier_id == "s1"


@pytest.mark.parametrize(
    "over,key",
    [
        (dict(invoice_number=None), "invoice_number"),
        (dict(lines=[]), "lines"),
        (dict(invoice_total=None), "invoice_total"),
        (dict(invoice_total="100.005"), "invoice_total"),
        (dict(currency="EUR"), "currency"),
        (dict(lines=[RawLine(description="Item", sku="CAB-1", quantity="0", unit_price="20.00", line_total="0.00")]), "lines[0].quantity"),
        (dict(lines=[RawLine(description="Item", sku=None, quantity="5", unit_price="20.00", line_total="100.00")]), "lines[0].sku"),
        (dict(lines=[RawLine(description="Item", sku="C", quantity="5", unit_price=None, line_total="100.00")]), "lines[0].unit_price"),
        (dict(lines=[RawLine(description="Item", sku="C", quantity="5", unit_price="20.00", line_total="x")]), "lines[0].line_total"),
    ],
)
def test_invalid_rules(over, key):
    assert key in normalize(raw(**over)).errors


@pytest.mark.parametrize("description", [None, "  "])
def test_missing_or_blank_description_is_valid(description):
    n = normalize(raw(lines=[RawLine(description=description, sku="C", quantity="5", unit_price="20.00", line_total="100.00")]))
    assert n.errors == {} and n.lines[0].errors == {} and n.lines[0].description is None


def test_currency_absent_ok():
    assert normalize(raw(currency=None)).errors == {}


def test_flags():
    n = normalize(raw(lines=[RawLine(description="Item", sku="C", quantity="5", unit_price="24.00", line_total="100.00")]))
    assert "line_total_mismatch" in n.flags
    n = normalize(raw(invoice_total="120.00"))
    assert "invoice_total_mismatch" in n.flags and not n.errors


def test_corrections_overlay_and_immutability():
    original = raw(lines=[RawLine(description="Item", sku="CAB-1", quantity="5", unit_price="24.00", line_total="120.00")], invoice_total="120.00")
    snapshot = original.model_copy(deep=True)
    corr = [Correction(field="lines[0].unit_price", original="24.00", corrected="20.00")]
    fixed = apply_corrections(original, corr)
    assert fixed.lines[0].unit_price == "20.00"
    assert original == snapshot
    # a correction passes the same normalization rules
    bad = effective_normalized(original, [Correction(field="po_id", corrected="PO-2"), Correction(field="invoice_total", corrected="1.234")])
    assert "invoice_total" in bad.errors and bad.po_id == "PO-2"
    with pytest.raises(ValueError):
        apply_corrections(original, [Correction(field="nonsense", corrected="x")])
