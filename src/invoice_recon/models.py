"""Pydantic models for extraction, normalization, reference data and reconciliation results."""

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["extraction_failed", "invalid", "duplicate", "unresolved", "discrepant", "reconciled"]
STATUSES: tuple[str, ...] = (
    "extraction_failed",
    "invalid",
    "duplicate",
    "unresolved",
    "discrepant",
    "reconciled",
)


# Layer 1: model output, strings exactly as printed.
class RawLine(BaseModel):
    sku: str | None = None
    description: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    line_total: str | None = None


class RawExtraction(BaseModel):
    invoice_number: str | None = None
    supplier_id: str | None = None
    po_id: str | None = None
    currency: str | None = None
    lines: list[RawLine] = Field(default_factory=list)
    invoice_total: str | None = None
    warnings: list[str] = Field(default_factory=list)


class Correction(BaseModel):
    field: str  # e.g. "po_id" or "lines[0].unit_price"
    original: str | None = None
    corrected: str | None = None
    reason: str = ""
    at: str = ""


# Layer 2: normalized values in integer cents.
class NormalizedLine(BaseModel):
    line_no: int
    sku: str | None = None
    description: str | None = None
    quantity: int | None = None
    unit_cents: int | None = None
    line_total_cents: int | None = None
    errors: dict[str, str] = Field(default_factory=dict)


class NormalizedInvoice(BaseModel):
    invoice_number: str | None = None
    supplier_id: str | None = None
    po_id: str | None = None
    currency: str | None = None
    lines: list[NormalizedLine] = Field(default_factory=list)
    invoice_total_cents: int | None = None
    errors: dict[str, str] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)


# Reference data.
class PoLine(BaseModel):
    line_no: int
    sku: str
    quantity: int
    unit_cents: int


class PurchaseOrder(BaseModel):
    po_id: str
    supplier_id: str
    lines: list[PoLine]
    source: str = ""


class ReceiptLine(BaseModel):
    sku: str
    quantity: int


class Receipt(BaseModel):
    receipt_id: str
    po_id: str
    lines: list[ReceiptLine]
    source: str = ""


# Results.
class Finding(BaseModel):
    code: str
    line_no: int | None = None
    detail: dict[str, int | str | None] = Field(default_factory=dict)


class LineResult(BaseModel):
    line_no: int
    sku: str | None = None
    po_line_no: int | None = None
    receipt_id: str | None = None
    ordered_qty: int | None = None
    received_qty: int | None = None
    billed_qty: int | None = None
    agreed_unit_cents: int | None = None
    billed_unit_cents: int | None = None
    expected_cents: int | None = None
    billed_cents: int | None = None
    difference_cents: int | None = None
    problems: list[str] = Field(default_factory=list)


class Reconciliation(BaseModel):
    status: Status
    expected_cents: int | None = None
    billed_cents: int | None = None
    difference_cents: int | None = None
    po_id: str | None = None
    po_source: str | None = None
    duplicate_of: str | None = None  # file_id of the original
    count_as_payable: bool = True
    lines: list[LineResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class BatchItem(BaseModel):
    """Input of reconcile_batch for one document."""

    file_id: str
    ingest_seq: int
    extraction_ok: bool
    extraction_error: str | None = None
    normalized: NormalizedInvoice | None = None


class BatchSummary(BaseModel):
    counts: dict[str, int]
    recoverable_cents: int
    net_difference_cents: int
