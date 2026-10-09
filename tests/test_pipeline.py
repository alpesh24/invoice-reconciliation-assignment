"""Phase 3 tests: storage, pipeline, CLI. Expected values come from domain.md / seed files / hand calculation."""

import json
from pathlib import Path

import pytest

from invoice_recon import cli, pipeline, storage
from invoice_recon.documents import DuplicateFileIdError, Document, discover_documents
from invoice_recon.extraction.base import ExtractionResult
from invoice_recon.models import BatchItem, Correction, RawExtraction, RawLine
from invoice_recon.reconcile import reconcile_batch

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "data" / "inputs"
SEED = json.loads((INPUTS / "seed.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((INPUTS / "expected-seed-results.json").read_text(encoding="utf-8"))
RECORDS = {r["file_id"]: r for r in SEED["invoices"]}
REFS = [INPUTS / "seed.json"]


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def raw_for(file_id: str) -> RawExtraction:
    rec = RECORDS[file_id]
    return RawExtraction(
        invoice_number=rec["invoice_number"], supplier_id=rec["supplier_id"], po_id=rec["po_id"], currency="USD",
        lines=[RawLine(sku=rec["sku"], description="Seed item", quantity=str(rec["quantity"]),
                       unit_price=money(rec["unit_cents"]), line_total=money(rec["total_cents"]))],
        invoice_total=money(rec["total_cents"]),
    )


def fake_extractor(file_id, path):
    if file_id in RECORDS:
        return ExtractionResult(status="ok", source="cached", raw=raw_for(file_id))
    return ExtractionResult(status="failed", error="no fake data")


def docs(*names: str) -> list[Document]:
    return [Document(file_id=n, path=INPUTS / "images" / f"{n}.png") for n in names]


def run(tmp_path, names, **kw):
    return pipeline.run_pipeline(
        documents=docs(*names), state_dir=tmp_path, reference_paths=REFS, extractor=fake_extractor, **kw
    )


def test_ingest_seq_assigned_once_persisted_and_not_reordered(tmp_path):
    states, _ = run(tmp_path, ["clean", "wrong-price"])
    assert [states[n].ingest_seq for n in ("clean", "wrong-price")] == [1, 2]
    # a second run with the documents in the opposite order must not reorder anything
    states, _ = run(tmp_path, ["wrong-price", "clean"])
    assert [states[n].ingest_seq for n in ("clean", "wrong-price")] == [1, 2]
    on_disk = storage.load_all(tmp_path)
    assert {n: s.ingest_seq for n, s in on_disk.items()} == {"clean": 1, "wrong-price": 2}
    stamp = on_disk["clean"].ingested_at
    # documents added later get later sequence numbers
    states, _ = run(tmp_path, ["wrong-price", "duplicate", "clean", "missing-reference"])
    assert states["duplicate"].ingest_seq == 3 and states["missing-reference"].ingest_seq == 4
    assert states["clean"].ingest_seq == 1 and states["clean"].ingested_at == stamp


def test_original_is_the_first_processed_even_when_listed_later(tmp_path):
    # duplicate processed first -> it is the original, clean becomes the duplicate (order on disk is irrelevant)
    states, _ = run(tmp_path, ["duplicate", "clean"])
    assert states["duplicate"].reconciliation.status == "reconciled"
    assert states["clean"].reconciliation.status == "duplicate"
    assert states["clean"].reconciliation.duplicate_of == "duplicate"


def test_seed_results_from_pipeline(tmp_path):
    states, summary = run(tmp_path, ["clean", "wrong-price", "duplicate", "missing-reference"])
    for exp in EXPECTED:
        got = states[exp["file_id"]].reconciliation.model_dump()
        for key, value in exp.items():
            if key != "file_id":
                assert got[key] == value, (exp["file_id"], key)
    assert summary.recoverable_cents == 2000 and summary.net_difference_cents == 2000
    assert storage.load_summary(tmp_path) == summary


def test_correction_persists_after_reload_and_recomputes_batch(tmp_path):
    run(tmp_path, ["clean", "wrong-price", "duplicate", "missing-reference"])
    # Correcting the duplicate's number changes its own status (cross-invoice recompute).
    pipeline.add_correction("duplicate", "invoice_number", "INV-9", "misread", state_dir=tmp_path, reference_paths=REFS)
    # Fix the wrong price completely: unit 20.00, line total 100.00, invoice total 100.00.
    for field, value in (("lines[0].unit_price", "20.00"), ("lines[0].line_total", "100.00"), ("invoice_total", "100.00")):
        pipeline.add_correction("wrong-price", field, value, "check", state_dir=tmp_path, reference_paths=REFS)

    reloaded = storage.load_all(tmp_path)  # simulates a restart
    assert reloaded["duplicate"].reconciliation.status == "reconciled"
    assert reloaded["wrong-price"].reconciliation.status == "reconciled"
    assert reloaded["wrong-price"].reconciliation.difference_cents == 0
    assert [c.field for c in reloaded["wrong-price"].corrections] == ["lines[0].unit_price", "lines[0].line_total", "invoice_total"]
    first = reloaded["wrong-price"].corrections[0]
    assert (first.original, first.corrected, first.reason) == ("24.00", "20.00", "check")
    assert storage.load_summary(tmp_path).recoverable_cents == 0
    # the original extraction is untouched
    assert reloaded["wrong-price"].extraction.raw.lines[0].unit_price == "24.00"


def test_corrections_and_review_survive_run_and_reconcile(tmp_path):
    run(tmp_path, ["wrong-price"])
    pipeline.add_correction("wrong-price", "po_id", "PO-1", "r", state_dir=tmp_path, reference_paths=REFS)
    pipeline.update_review("wrong-price", "in_review", "looking", state_dir=tmp_path)
    run(tmp_path, ["wrong-price"])
    pipeline.reconcile_all(state_dir=tmp_path, reference_paths=REFS)
    state = storage.load_invoice("wrong-price", tmp_path)
    assert len(state.corrections) == 1 and state.review.status == "in_review" and state.review.comment == "looking"
    assert state.normalized.po_id == "PO-1"


def test_failed_extraction_is_retried_and_does_not_stop_batch(tmp_path):
    calls = []

    def flaky(file_id, path):
        calls.append(file_id)
        if file_id == "clean" and calls.count("clean") == 1:
            raise RuntimeError("boom")
        return fake_extractor(file_id, path)

    kw = dict(documents=docs("clean", "wrong-price"), state_dir=tmp_path, reference_paths=REFS, extractor=flaky)
    states, summary = pipeline.run_pipeline(**kw)
    assert states["clean"].reconciliation.status == "extraction_failed"
    assert "boom" in states["clean"].reconciliation.error
    assert states["wrong-price"].reconciliation.status == "discrepant"
    states, _ = pipeline.run_pipeline(**kw)
    assert states["clean"].reconciliation.status == "reconciled" and states["clean"].ingest_seq == 1
    assert calls.count("wrong-price") == 1  # a successful extraction is kept, not repeated


def test_invalid_correction_target_is_rejected_and_nothing_saved(tmp_path):
    run(tmp_path, ["clean"])
    for field in ("lines[3].sku", "nonsense"):
        with pytest.raises(ValueError):
            pipeline.add_correction("clean", field, "x", "r", state_dir=tmp_path, reference_paths=REFS)
    assert storage.load_invoice("clean", tmp_path).corrections == []
    with pytest.raises(ValueError):
        pipeline.add_correction("nope", "po_id", "PO-1", "r", state_dir=tmp_path, reference_paths=REFS)


def test_saved_correction_that_cannot_apply_becomes_invalid_not_a_crash(tmp_path):
    run(tmp_path, ["clean", "wrong-price"])
    state = storage.load_invoice("clean", tmp_path)
    state.corrections.append(Correction(field="lines[7].sku", corrected="X"))  # hand-edited state file
    storage.save_invoice(state, tmp_path)
    states, _ = pipeline.reconcile_all(state_dir=tmp_path, reference_paths=REFS)
    rec = states["clean"].reconciliation
    assert rec.status == "invalid" and "corrections" in rec.errors and "lines[7]" in rec.errors["corrections"]
    assert states["wrong-price"].reconciliation.status == "discrepant"


def test_extraction_ok_without_normalized_gets_explicit_error():
    item = BatchItem(file_id="a", ingest_seq=1, extraction_ok=True, normalized=None)
    results, _ = reconcile_batch([item], [], [])
    assert results["a"].status == "invalid" and results["a"].errors


def test_atomic_write_leaves_no_tmp_file(tmp_path):
    run(tmp_path, ["clean"])
    assert not list(tmp_path.rglob("*.tmp"))


def test_unreadable_state_file_raises_storage_error(tmp_path):
    run(tmp_path, ["clean"])
    storage.invoice_path("clean", tmp_path).write_text("{not json", encoding="utf-8")
    with pytest.raises(storage.StorageError):
        storage.load_all(tmp_path)


def test_discover_order_and_unique_file_ids(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    for name in ("z.png", "m.png"):
        (a / name).write_bytes(b"x")
    (b / "c.jpg").write_bytes(b"x")
    (a / "notes.txt").write_text("x")
    assert [d.file_id for d in discover_documents([a, b, tmp_path / "missing"])] == ["m", "z", "c"]
    (b / "m.png").write_bytes(b"x")
    with pytest.raises(DuplicateFileIdError):
        discover_documents([a, b])


def test_discover_real_inputs_in_filename_order():
    ids = [d.file_id for d in discover_documents([INPUTS / "images"])]
    assert ids == ["clean", "duplicate", "missing-reference", "wrong-price"]


def test_end_to_end_replay_from_cache(tmp_path):
    """Real replay: images -> cache -> pipeline; no key, no network."""
    states, summary = pipeline.run_pipeline(
        documents=discover_documents([INPUTS / "images"]), state_dir=tmp_path, reference_paths=REFS
    )
    assert all(s.extraction.source == "cached" for s in states.values())
    # clean is processed before duplicate (filename order), so clean is the original
    for exp in EXPECTED:
        got = states[exp["file_id"]].reconciliation.model_dump()
        for key, value in exp.items():
            if key != "file_id":
                assert got[key] == value, (exp["file_id"], key)
    assert summary.recoverable_cents == 2000


def test_cli_run_reconcile_reset(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(storage.config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(pipeline.config, "INPUTS_DIR", INPUTS)
    monkeypatch.setattr(pipeline, "default_extractor", lambda: fake_extractor)
    monkeypatch.setattr(pipeline, "default_reference_paths", lambda: REFS)
    assert cli.main(["reset"]) == 2  # needs --yes
    assert cli.main(["reconcile"]) == 1  # nothing saved yet
    assert cli.main(["run"]) == 0
    out = capsys.readouterr().out
    assert "wrong-price" in out and "recoverable USD 20.00" in out
    assert cli.main(["reconcile"]) == 0
    assert (tmp_path / "state" / "summary.json").is_file()
    assert cli.main(["reset", "--yes"]) == 0
    assert not (tmp_path / "state").exists()
