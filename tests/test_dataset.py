"""Phase 6 tests: generated dataset integrity and expected results.

Expected values are hand-calculated from domain.md and docs/DATASET.md. Tests may read invoice records.
"""

import json
import subprocess
import sys
from pathlib import Path

from invoice_recon.models import BatchItem, RawExtraction, RawLine
from invoice_recon.normalize import normalize
from invoice_recon.reconcile import reconcile_batch
from invoice_recon.reference import parse_reference

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
EXPECTED_PATH = ROOT / "data" / "expected" / "expected-results.json"
SEED = json.loads((ROOT / "data" / "inputs" / "seed.json").read_text(encoding="utf-8"))
REF = json.loads((GEN / "reference.json").read_text(encoding="utf-8"))
RECORDS = json.loads((GEN / "invoice-records.json").read_text(encoding="utf-8"))
EXPECTED = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


def money(c: int) -> str:
    return f"{c // 100}.{c % 100:02d}"


def test_record_arithmetic_and_images_exist():
    for r in RECORDS:
        for ln in r["lines"]:
            assert ln["quantity"] * ln["unit_cents"] == ln["line_total_cents"], r["file_id"]
        assert sum(ln["line_total_cents"] for ln in r["lines"]) == r["total_cents"], r["file_id"]
        assert (GEN / "images" / f"{r['file_id']}.png").is_file()


def test_relationships_by_id():
    po_ids = {p["po_id"] for p in SEED["purchase_orders"] + REF["purchase_orders"]}
    assert {r["po_id"] for r in REF["receipts"]} == {p["po_id"] for p in REF["purchase_orders"]}
    assert po_ids == {"PO-1", "PO-2", "PO-3", "PO-4", "PO-5"}
    for r in RECORDS:
        assert r["po_id"] in po_ids


def test_expected_hand_values():
    by = {c["file_id"]: c for c in EXPECTED["cases"]}
    m = by["multi-line-price"]["before_correction"]
    assert (m["expected_cents"], m["billed_cents"], m["difference_cents"]) == (26000, 27000, 1000)
    s = by["short-receipt"]["before_correction"]
    assert (s["status"], s["expected_cents"], s["difference_cents"]) == ("discrepant", 24300, 0)
    # hand check: ordered 6, received 4, billed 6 -> received < ordered (A1) and billed > received (domain rule 3)
    assert {k: sorted(v) for k, v in s["line_findings"].items()} == {"CAB-1": ["qty_over_received", "short_receipt"]}
    c = by["conflicting-supplier"]["before_correction"]
    assert (c["status"], c["expected_cents"], c["difference_cents"]) == ("unresolved", None, None)
    k = by["correction"]["before_correction"]
    assert (k["status"], k["expected_cents"], k["difference_cents"]) == ("unresolved", None, None)
    a = by["correction"]["after_correction"]
    assert (a["status"], a["expected_cents"], a["billed_cents"], a["difference_cents"]) == ("reconciled", 31000, 31000, 0)
    assert EXPECTED["summary_before_correction"]["status_counts"] == {"reconciled": 1, "discrepant": 3, "duplicate": 1, "unresolved": 3}
    assert EXPECTED["summary_after_correction"]["status_counts"] == {"reconciled": 2, "discrepant": 3, "duplicate": 1, "unresolved": 2}
    assert EXPECTED["summary_before_correction"]["recoverable_cents"] == 3000
    assert EXPECTED["summary_after_correction"]["recoverable_cents"] == 3000


def test_compute_expected_is_reproducible_and_independent_of_src():
    text = (ROOT / "scripts" / "compute_expected.py").read_text(encoding="utf-8")
    assert "invoice_recon" not in text
    before = EXPECTED_PATH.read_text(encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "compute_expected.py")], check=True, capture_output=True)
    assert EXPECTED_PATH.read_text(encoding="utf-8") == before


def test_application_rules_agree_with_expected_on_generated_records():
    """Feed structured records (no model) through reconcile_batch; compare with the independent expected file."""
    orders, receipts = parse_reference({k: SEED[k] for k in ("purchase_orders", "receipts")})
    o2, r2 = parse_reference(REF)
    orders, receipts = orders + o2, receipts + r2
    seed_recs = [
        {"file_id": s["file_id"], "invoice_number": s["invoice_number"], "supplier_id": s["supplier_id"],
         "po_id": s["po_id"], "total_cents": s["total_cents"],
         "lines": [{"sku": s["sku"], "quantity": s["quantity"], "unit_cents": s["unit_cents"],
                    "line_total_cents": s["total_cents"]}]}
        for s in SEED["invoices"]
    ]
    recs = sorted(seed_recs, key=lambda r: r["file_id"]) + sorted(RECORDS, key=lambda r: r["file_id"])

    def run(po_override):
        items = []
        for seq, r in enumerate(recs, start=1):
            po = po_override.get(r["file_id"], r["po_id"])
            raw = RawExtraction(
                invoice_number=r["invoice_number"], supplier_id=r["supplier_id"], po_id=po, currency="USD",
                lines=[RawLine(sku=ln["sku"], quantity=str(ln["quantity"]), unit_price=money(ln["unit_cents"]),
                               line_total=money(ln["line_total_cents"])) for ln in r["lines"]],
                invoice_total=money(r["total_cents"]))
            items.append(BatchItem(file_id=r["file_id"], ingest_seq=seq, extraction_ok=True, normalized=normalize(raw)))
        return reconcile_batch(items, orders, receipts)[0]

    for key, override in (("before_correction", {"correction": "PO-S"}), ("after_correction", {})):
        results = run(override)
        for case in EXPECTED["cases"]:
            exp = case.get(key) or case["before_correction"]
            got = results[case["file_id"]]
            assert got.status == exp["status"], (key, case["file_id"], got.status)
            for f in ("expected_cents", "difference_cents"):
                if f in exp:
                    assert getattr(got, f) == exp[f], (key, case["file_id"], f)
