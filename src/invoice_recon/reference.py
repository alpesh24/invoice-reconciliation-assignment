"""Load purchase orders and receipts (flat seed format and lines format). Never reads invoices."""

import json
from pathlib import Path

from .models import PoLine, PurchaseOrder, Receipt, ReceiptLine


def parse_reference(data: dict, source: str = "") -> tuple[list[PurchaseOrder], list[Receipt]]:
    """Pure: convert a decoded reference document. Only purchase_orders and receipts are read."""
    orders = []
    for po in data.get("purchase_orders", []):
        raw_lines = po["lines"] if "lines" in po else [po]
        lines = [
            PoLine(line_no=i, sku=ln["sku"], quantity=ln["quantity"], unit_cents=ln["unit_cents"])
            for i, ln in enumerate(raw_lines, start=1)
        ]
        orders.append(PurchaseOrder(po_id=po["po_id"], supplier_id=po["supplier_id"], lines=lines, source=source))
    receipts = []
    for rc in data.get("receipts", []):
        raw_lines = rc["lines"] if "lines" in rc else [rc]
        lines = [ReceiptLine(sku=ln["sku"], quantity=ln["quantity"]) for ln in raw_lines]
        receipts.append(Receipt(receipt_id=rc["receipt_id"], po_id=rc["po_id"], lines=lines, source=source))
    return orders, receipts


def load_reference_file(path: Path) -> tuple[list[PurchaseOrder], list[Receipt]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):  # placeholder file (e.g. `null`) before the dataset phase
        return [], []
    subset ={key: data[key] for key in ("purchase_orders", "receipts") if key in data}
    return parse_reference(subset, str(path))


def load_reference(paths: list[Path]) -> tuple[list[PurchaseOrder], list[Receipt]]:
    """Load and concatenate several reference files; missing files are skipped."""
    orders: list[PurchaseOrder] = []
    receipts: list[Receipt] = []
    for path in paths:
        if path.is_file():
            o, r = load_reference_file(path)
            orders += o
            receipts += r
    return orders, receipts
