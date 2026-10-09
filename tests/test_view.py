"""Phase 4 tests: pure view-models, tolerant loading, UI smoke. Expected values from seed files / hand calculation."""

import json
from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest

from invoice_recon import pipeline, storage, view
from invoice_recon.documents import Document
from invoice_recon.extraction.base import ExtractionResult
from invoice_recon.models import RawExtraction, RawLine
from invoice_recon.reference import load_reference

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "data" / "inputs"
SEED = json.loads((INPUTS / "seed.json").read_text(encoding="utf-8"))
RECORDS = {r["file_id"]: r for r in SEED["invoices"]}
REFS = [INPUTS / "seed.json"]
NAMES = ["clean", "wrong-price", "duplicate", "missing-reference"]


def _money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def fake_extractor(file_id, path):
    rec = RECORDS[file_id]
    raw = RawExtraction(
        invoice_number=rec["invoice_number"], supplier_id=rec["supplier_id"], po_id=rec["po_id"], currency="USD",
        lines=[RawLine(sku=rec["sku"], description="x", quantity=str(rec["quantity"]),
                       unit_price=_money(rec["unit_cents"]), line_total=_money(rec["total_cents"]))],
        invoice_total=_money(rec["total_cents"]),
    )
    return ExtractionResult(status="ok", source="cached", raw=raw)


@pytest.fixture
def states(tmp_path):
    docs = [Document(file_id=n, path=INPUTS / "images" / f"{n}.png") for n in NAMES]
    pipeline.run_pipeline(documents=docs, state_dir=tmp_path, reference_paths=REFS, extractor=fake_extractor)
    return tmp_path


def test_queue_rows_follow_ingest_order_and_format_money(states):
    loaded = storage.load_all(states)
    rows = view.queue_rows(loaded)
    assert [r["file_id"] for r in rows] == NAMES
    wp = next(r for r in rows if r["file_id"] == "wrong-price")
    assert (wp["status"], wp["difference"], wp["invoice_number"], wp["po_id"]) == ("discrepant", "$20.00", "INV-2", "PO-2")
    assert next(r for r in rows if r["file_id"] == "missing-reference")["difference"] == "-"
    assert next(r for r in rows if r["file_id"] == "clean")["difference"] == "$0.00"


def test_filter_by_status_and_review(states):
    loaded = storage.load_all(states)
    rows = view.queue_rows(loaded)
    assert [r["file_id"] for r in view.filter_rows(rows, ["discrepant"])] == ["wrong-price"]
    assert {r["file_id"] for r in view.filter_rows(rows, ["duplicate", "unresolved"])} == {"duplicate", "missing-reference"}
    assert view.filter_rows(rows) == rows and view.filter_rows(rows, [], []) == rows
    assert view.filter_rows(rows, review=["done"]) == []


def test_comparison_shows_original_and_effective_after_correction(states):
    pipeline.add_correction("wrong-price", "lines[0].unit_price", "20.00", "check", state_dir=states, reference_paths=REFS)
    state = storage.load_all(states)["wrong-price"]
    rows = {r["field"]: r for r in view.raw_comparison_rows(state.extraction.raw, state)}
    assert rows["lines[0].unit_price"] == {
        "field": "lines[0].unit_price", "original": "24.00", "effective": "20.00", "changed": "corrected"}
    assert rows["po_id"]["changed"] == "" and rows["po_id"]["original"] == "PO-2"
    assert view.correction_history_rows(state)[0]["original"] == "24.00"
    assert view.queue_row(state)["corrected"] == "yes"


def test_line_and_finding_rows_for_wrong_price(states):
    state = storage.load_all(states)["wrong-price"]
    line = view.line_table_rows(state)[0]
    assert (line["ordered qty"], line["received qty"], line["billed qty"]) == ("5", "5", "5")
    assert (line["agreed unit"], line["billed unit"]) == ("$20.00", "$24.00")
    assert (line["expected"], line["billed"], line["difference"]) == ("$100.00", "$120.00", "$20.00")
    findings = view.finding_rows(state)
    assert [f["finding"] for f in findings] == ["price_diff"]
    assert findings[0]["detail"] == "billed_unit_cents=$24.00, agreed_unit_cents=$20.00"


def test_unresolved_has_dashes_and_no_po(states):
    loaded = storage.load_all(states)
    state = loaded["missing-reference"]
    assert state.reconciliation.status == "unresolved"
    assert view.finding_rows(state)[0]["finding"] == "missing_reference"
    orders, receipts = load_reference(REFS)
    assert view.matched_po(state, orders) is None


def test_matched_po_and_receipt_rows(states):
    state = storage.load_all(states)["wrong-price"]
    orders, receipts = load_reference(REFS)
    po = view.matched_po(state, orders)
    assert po is not None and po.po_id == "PO-2"
    assert view.po_rows(po) == [{"line": "1", "sku": "CAB-1", "quantity": "5", "unit price": "$20.00"}]
    assert view.receipt_rows("PO-2", receipts) == [{"receipt": "RC-2", "sku": "CAB-1", "quantity": "5"}]


def test_correctable_fields_match_what_the_pipeline_accepts():
    raw = RawExtraction(lines=[RawLine(), RawLine()])
    names = view.correctable_fields(raw)
    assert "invoice_total" in names and "lines[1].unit_price" in names and len(names) == 5 + 2 * 5
    from invoice_recon.normalize import get_raw_value

    for n in names:
        get_raw_value(raw, n)  # raises ValueError if the UI offered a field the backend rejects


def test_summary_finding_counts(states):
    loaded = storage.load_all(states)
    assert view.summary_finding_counts(loaded) == {"duplicate_invoice": 1, "missing_reference": 1, "price_diff": 1}


def test_provenance_labels_never_present_simulated_as_real():
    assert "SIMULATED" in view.provenance_label("simulated") and "not a real" in view.provenance_label("simulated")
    assert view.provenance_label("cached").startswith("CACHED")
    assert view.provenance_label(None) == "no model response"


def test_load_all_tolerant_reports_corrupt_file_and_keeps_others(states):
    (states / "invoices" / "clean.json").write_text("{not json", encoding="utf-8")
    loaded, errors = storage.load_all_tolerant(states)
    assert set(errors) == {"clean"} and "Unreadable state file" in errors["clean"]
    assert set(loaded) == {"wrong-price", "duplicate", "missing-reference"}
    with pytest.raises(storage.StorageError):  # the pipeline stays strict so it never recreates a corrupt document
        storage.load_all(states)


def test_ui_pages_render_without_exceptions(states, monkeypatch):

    monkeypatch.setattr("invoice_recon.config.STATE_DIR", states)
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=30)
    at.run()
    assert not at.exception
    for page in ("Invoice detail", "Summary", "Queue"):
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, page


def test_ui_correction_form_saves_and_reconciles(states, monkeypatch):

    monkeypatch.setattr("invoice_recon.config.STATE_DIR", states)
    monkeypatch.setattr(pipeline, "default_reference_paths", lambda: REFS)
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value("Invoice detail").run()
    at.selectbox(key="selected").set_value("wrong-price").run()
    form_field = next(s for s in at.selectbox if s.label == "Field")
    form_field.set_value("lines[0].unit_price")
    next(t for t in at.text_input if t.label == "New value (as printed on the invoice)").set_value("20.00")
    next(t for t in at.text_input if t.label == "Reason").set_value("checked image")
    next(b for b in at.button if "Save correction" in b.label).click().run()
    assert not at.exception
    saved = storage.load_all(states)["wrong-price"]
    assert [(c.field, c.original, c.corrected) for c in saved.corrections] == [("lines[0].unit_price", "24.00", "20.00")]
    assert saved.extraction.raw.lines[0].unit_price == "24.00"
