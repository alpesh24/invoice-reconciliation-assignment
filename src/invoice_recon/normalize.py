"""RawExtraction (+ corrections) -> NormalizedInvoice. Pure."""

import re

from .models import Correction, NormalizedInvoice, NormalizedLine, RawExtraction
from .money import MoneyError, parse_money, parse_quantity


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def normalize(raw: RawExtraction) -> NormalizedInvoice:
    errors: dict[str, str] = {}
    flags: list[str] = []

    invoice_number = _clean(raw.invoice_number)
    if invoice_number is None:
        errors["invoice_number"] = "missing"
    currency = _clean(raw.currency)
    if currency is not None and currency != "USD":
        errors["currency"] = f"must be USD, got {currency!r}"
    if not raw.lines:
        errors["lines"] = "no lines"

    lines: list[NormalizedLine] = []
    for i, rl in enumerate(raw.lines):
        line = NormalizedLine(line_no=i + 1, sku=_clean(rl.sku), description=_clean(rl.description))
        if line.sku is None:
            line.errors["sku"] = "missing"
        for name, text, parser in (
            ("quantity", rl.quantity, parse_quantity),
            ("unit_price", rl.unit_price, parse_money),
            ("line_total", rl.line_total, parse_money),
        ):
            try:
                value = parser(_clean(text))
            except MoneyError as exc:
                line.errors[name] = str(exc)
                continue
            if name == "quantity":
                line.quantity = value
            elif name == "unit_price":
                line.unit_cents = value
            else:
                line.line_total_cents = value
        for name, reason in line.errors.items():
            errors[f"lines[{i}].{name}"] = reason
        lines.append(line)

    invoice_total = None
    try:
        invoice_total = parse_money(_clean(raw.invoice_total))
    except MoneyError as exc:
        errors["invoice_total"] = str(exc)

    # Internal consistency checks are flags, not errors.
    if any(
        ln.quantity is not None
        and ln.unit_cents is not None
        and ln.line_total_cents is not None
        and ln.quantity * ln.unit_cents != ln.line_total_cents
        for ln in lines
    ):
        flags.append("line_total_mismatch")
    if invoice_total is not None and lines and all(ln.line_total_cents is not None for ln in lines):
        if sum(ln.line_total_cents for ln in lines) != invoice_total:
            flags.append("invoice_total_mismatch")

    return NormalizedInvoice(
        invoice_number=invoice_number,
        supplier_id=_clean(raw.supplier_id),
        po_id=_clean(raw.po_id),
        currency=currency,
        lines=lines,
        invoice_total_cents=invoice_total,
        errors=errors,
        flags=flags,
    )


_LINE_FIELD = re.compile(r"^lines\[(\d+)\]\.(sku|description|quantity|unit_price|line_total)$")
_TOP_FIELDS = {"invoice_number", "supplier_id", "po_id", "currency", "invoice_total"}


def get_raw_value(raw: RawExtraction, field: str) -> str | None:
    """Current raw string of a correctable field; ValueError for an unknown field or missing line."""
    match = _LINE_FIELD.match(field)
    if match:
        index = int(match.group(1))
        if index >= len(raw.lines):
            raise ValueError(f"correction targets missing line: {field}")
        return getattr(raw.lines[index], match.group(2))
    if field in _TOP_FIELDS:
        return getattr(raw, field)
    raise ValueError(f"unknown correction field: {field}")


def apply_corrections(raw: RawExtraction, corrections: list[Correction]) -> RawExtraction:
    """Return a copy of raw with corrections applied in order; the original is never mutated."""
    result = raw.model_copy(deep=True)
    for c in corrections:
        match = _LINE_FIELD.match(c.field)
        if match:
            index = int(match.group(1))
            if index >= len(result.lines):
                raise ValueError(f"correction targets missing line: {c.field}")
            setattr(result.lines[index], match.group(2), c.corrected)
        elif c.field in _TOP_FIELDS:
            setattr(result, c.field, c.corrected)
        else:
            raise ValueError(f"unknown correction field: {c.field}")
    return result


def effective_normalized(raw: RawExtraction, corrections: list[Correction]) -> NormalizedInvoice:
    return normalize(apply_corrections(raw, corrections))
