"""Compute expected results independently of the application (no import from src/).

Inputs : data/inputs/seed.json (purchase orders, receipts, seed invoice records),
         data/generated/reference.json, data/generated/invoice-records.json.
Output : data/expected/expected-results.json
Rules  : data/inputs/domain.md (rules 1-4) and docs/DECISIONS.md (A1, A4, A6, C4, C7).
Also cross-checks the seed cases against data/inputs/expected-seed-results.json.
Run: python scripts/compute_expected.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "data" / "inputs"
GEN = ROOT / "data" / "generated"
OUT = ROOT / "data" / "expected" / "expected-results.json"

# Documented correction for the M5 case: file_id -> (field, simulated wrong value, corrected value)
CORRECTIONS = {"correction": ("po_id", "PO-S", "PO-5")}


def load_inputs():
    seed = json.loads((INPUTS / "seed.json").read_text(encoding="utf-8"))
    ref = json.loads((GEN / "reference.json").read_text(encoding="utf-8"))
    gen = json.loads((GEN / "invoice-records.json").read_text(encoding="utf-8"))
    pos: dict[tuple[str, str], dict[str, tuple[int, int]]] = {}  # (supplier, po) -> sku -> (qty, unit)
    for po in seed["purchase_orders"]:
        pos.setdefault((po["supplier_id"], po["po_id"]), {})[po["sku"]] = (po["quantity"], po["unit_cents"])
    for po in ref["purchase_orders"]:
        pos[(po["supplier_id"], po["po_id"])] = {ln["sku"]: (ln["quantity"], ln["unit_cents"]) for ln in po["lines"]}
    po_ids = {po_id for _, po_id in pos}
    rcpt: dict[tuple[str, str], int] = {}
    for rc in seed["receipts"]:
        rcpt[(rc["po_id"], rc["sku"])] = rc["quantity"]
    for rc in ref["receipts"]:
        for ln in rc["lines"]:
            rcpt[(rc["po_id"], ln["sku"])] = ln["quantity"]
    records = []
    for r in seed["invoices"]:  # seed records have a single line
        records.append({**{k: r[k] for k in ("file_id", "invoice_number", "supplier_id", "po_id", "total_cents", "layout")},
                        "lines": [{"sku": r["sku"], "quantity": r["quantity"], "unit_cents": r["unit_cents"],
                                   "line_total_cents": r["total_cents"]}], "origin": "seed"})
    records += [{**r, "origin": "generated"} for r in gen]
    # Processing order = filename order within data/inputs/images, then data/generated/images.
    seed_ids = sorted(r["file_id"] for r in records if r["origin"] == "seed")
    gen_ids = sorted(r["file_id"] for r in records if r["origin"] == "generated")
    by_id = {r["file_id"]: r for r in records}
    return [by_id[i] for i in seed_ids + gen_ids], pos, po_ids, rcpt


def evaluate(records, pos, po_ids, rcpt, override=None):
    """Return {file_id: result}. override = {file_id: {field: value}} applies a changed field."""
    override = override or {}
    results, seen = {}, {}
    for rec in records:
        rec = {**rec, **override.get(rec["file_id"], {})}
        res = {"file_id": rec["file_id"], "invoice_number": rec["invoice_number"],
               "supplier_id": rec["supplier_id"], "po_id": rec["po_id"], "line_findings": {}}
        key = (rec["supplier_id"], rec["invoice_number"])
        if key in seen:  # domain rule 4 / C5: first processed is the original; A6: duplicate wins
            res.update(status="duplicate", count_as_payable=False, duplicate_of=seen[key], recoverable_cents=0,
                       rule="domain.md rule 4; DECISIONS C4, C5, A6")
            results[rec["file_id"]] = res
            continue
        seen[key] = rec["file_id"]
        billed = rec["total_cents"]
        if rec["supplier_id"] is None or rec["po_id"] is None:
            res.update(status="unresolved", reason="missing_reference", rule="domain.md rule 2; DECISIONS E6")
        elif (rec["supplier_id"], rec["po_id"]) not in pos:
            reason = "conflicting_reference" if rec["po_id"] in po_ids else "unknown_po"
            res.update(status="unresolved", reason=reason, rule="domain.md rule 2; DECISIONS A4")
        else:
            po = pos[(rec["supplier_id"], rec["po_id"])]
            expected, bad = 0, False
            for ln in rec["lines"]:
                if ln["sku"] not in po:
                    res["line_findings"][ln["sku"]] = ["sku_not_on_po"]
                    bad = True
                    continue
                qty, unit = po[ln["sku"]]
                expected += qty * unit  # domain rule 3: ordered qty x agreed unit price
                recv = rcpt.get((rec["po_id"], ln["sku"]))
                found = []
                if recv is None:
                    found.append("no_receipt")
                    bad = True
                else:
                    if recv < qty:
                        found.append("short_receipt")  # DECISIONS A1
                    if ln["quantity"] > recv:
                        found.append("qty_over_received")  # domain rule 3: billed vs received quantity
                    if ln["quantity"] > qty:
                        found.append("qty_over_ordered")
                    if ln["quantity"] < qty:
                        found.append("qty_under_ordered")
                if ln["unit_cents"] != unit:
                    found.append("price_differs")
                if found:
                    res["line_findings"][ln["sku"]] = found
            if bad:
                res.update(status="unresolved", reason="unmatched_line_or_receipt", rule="DECISIONS A8, C6")
            else:
                diff = billed - expected
                res.update(expected_cents=expected, billed_cents=billed, difference_cents=diff,
                           status="reconciled" if diff == 0 and not res["line_findings"] else "discrepant",
                           rule="domain.md rule 3 and 4; DECISIONS C2, C3, C7, A1")
                res["recoverable_cents"] = diff if res["status"] == "discrepant" and diff > 0 else 0
        if res["status"] == "unresolved":
            res.update(expected_cents=None, billed_cents=billed, difference_cents=None, recoverable_cents=0)
        res["count_as_payable"] = res["status"] != "duplicate"  # DECISIONS Q-P7-1: false only for duplicates
        results[rec["file_id"]] = res
    return results


def summary(results):
    counts = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"status_counts": counts, "recoverable_cents": sum(r.get("recoverable_cents", 0) for r in results.values())}


def main() -> None:
    records, pos, po_ids, rcpt = load_inputs()
    # Records hold the true printed value; "before" applies the simulated misread, "after" the correction.
    misread = {fid: {field: wrong} for fid, (field, wrong, _fixed) in CORRECTIONS.items()}
    fixed = {fid: {field: right} for fid, (field, _wrong, right) in CORRECTIONS.items()}
    before = evaluate(records, pos, po_ids, rcpt, misread)
    after = evaluate(records, pos, po_ids, rcpt, fixed)

    seed_expected = json.loads((INPUTS / "expected-seed-results.json").read_text(encoding="utf-8"))
    for exp in seed_expected:  # cross-check seed cases against the supplied answers
        for k, v in exp.items():
            assert before[exp["file_id"]].get(k) == v, (exp["file_id"], k, before[exp["file_id"]].get(k), v)

    cases = []
    for rec in records:
        fid = rec["file_id"]
        entry = {"file_id": fid, "origin": rec["origin"], "before_correction": before[fid]}
        if fid in CORRECTIONS:
            field, wrong, right = CORRECTIONS[fid]
            entry["correction"] = {"field": field, "from": wrong, "to": right}
            entry["after_correction"] = after[fid]
        cases.append(entry)
    doc = {
        "note": "Computed by scripts/compute_expected.py from structured records; independent of src/.",
        "reference_cases": {"M1": "clean", "M2": "wrong-price", "M3": "duplicate", "M4": "missing-reference", "M5": "correction"},
        "cases": cases,
        "summary_before_correction": summary(before),
        "summary_after_correction": summary(after),
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT)
    print("before:", doc["summary_before_correction"])
    print("after: ", doc["summary_after_correction"])


if __name__ == "__main__":
    main()
