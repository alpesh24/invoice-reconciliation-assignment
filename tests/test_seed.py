"""Seed test: structured seed records -> RawExtraction -> normalize -> reconcile_batch vs expected results.

Tests may read seed.json["invoices"] and expected-seed-results.json; application code may not.
"""

import json
from pathlib import Path

from invoice_recon.models import BatchItem, RawExtraction, RawLine
from invoice_recon.normalize import normalize
from invoice_recon.reconcile import reconcile_batch
from invoice_recon.reference import parse_reference

INPUTS = Path(__file__).resolve().parents[1] / "data" / "inputs"


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def raw_from_record(rec: dict) -> RawExtraction:
    return RawExtraction(
        invoice_number=rec["invoice_number"],
        supplier_id=rec["supplier_id"],
        po_id=rec["po_id"],
        currency="USD",
        lines=[RawLine(sku=rec["sku"], description="Seed item", quantity=str(rec["quantity"]),
                       unit_price=money(rec["unit_cents"]), line_total=money(rec["total_cents"]))],
        invoice_total=money(rec["total_cents"]),
    )


def test_seed_results_reproduced_without_model():
    seed = json.loads((INPUTS / "seed.json").read_text(encoding="utf-8"))
    expected = json.loads((INPUTS / "expected-seed-results.json").read_text(encoding="utf-8"))
    orders, receipts = parse_reference({k: seed[k] for k in ("purchase_orders", "receipts")})
    items = [
        BatchItem(file_id=rec["file_id"], ingest_seq=seq, extraction_ok=True, normalized=normalize(raw_from_record(rec)))
        for seq, rec in enumerate(seed["invoices"], start=1)
    ]
    results, _ = reconcile_batch(items, orders, receipts)
    assert len(expected) == 4
    for exp in expected:
        got = results[exp["file_id"]].model_dump()
        for key, value in exp.items():
            if key != "file_id":
                assert got[key] == value, (exp["file_id"], key, got[key], value)
