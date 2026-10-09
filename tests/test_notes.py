"""Phase 5 tests: number guard, notes only for non-reconciled invoices, insight aggregates, provenance.

Expected values come from data/inputs/domain.md, expected-seed-results.json and hand calculation.
"""

import json
from pathlib import Path

import pytest

from invoice_recon import insights, notes, pipeline, storage
from invoice_recon.documents import Document
from invoice_recon.extraction import cache as cache_mod
from invoice_recon.extraction.base import ExtractionResult
from invoice_recon.models import BatchSummary, Finding, LineResult, NormalizedInvoice, RawExtraction, RawLine, Reconciliation
from invoice_recon.storage import InvoiceState

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "data" / "inputs"
SEED = json.loads((INPUTS / "seed.json").read_text(encoding="utf-8"))
RECORDS = {r["file_id"]: r for r in SEED["invoices"]}
REFS = [INPUTS / "seed.json"]
NAMES = ["clean", "wrong-price", "duplicate", "missing-reference"]


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def fake_extractor(file_id, path):
    rec = RECORDS[file_id]
    raw = RawExtraction(
        invoice_number=rec["invoice_number"], supplier_id=rec["supplier_id"], po_id=rec["po_id"], currency="USD",
        lines=[RawLine(sku=rec["sku"], description=None, quantity=str(rec["quantity"]),
                       unit_price=money(rec["unit_cents"]), line_total=money(rec["total_cents"]))],
        invoice_total=money(rec["total_cents"]),
    )
    return ExtractionResult(status="ok", source="cached", raw=raw)


@pytest.fixture
def seed_states(tmp_path, monkeypatch):
    # Hermetic: real notes cached in data/model_cache (live runs) must not change what these tests see.
    monkeypatch.setattr("invoice_recon.config.MODEL_CACHE_DIR", tmp_path / "empty-model-cache")
    docs = [Document(file_id=n, path=INPUTS / "images" / f"{n}.png") for n in NAMES]
    states, summary = pipeline.run_pipeline(
        documents=docs, state_dir=tmp_path, reference_paths=REFS, extractor=fake_extractor,
        note_provider=None,
    )
    return states, summary, tmp_path


class ExplodingProvider:
    def generate_text(self, prompt, model):
        raise AssertionError("a model must not be called")


class FixedProvider:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def generate_text(self, prompt, model):
        self.calls += 1
        return self.text


# --- number guard ---------------------------------------------------------------------------------------------

def wrong_price_payload(seed_states):
    states, _, _ = seed_states
    return notes.findings_payload(states["wrong-price"])


GOOD = (
    "DRAFT — Invoice INV-2 (supplier S1, PO PO-2) was billed $120.00 against an expected $100.00. "
    "The difference of $20.00 comes from the unit price on line 1. "
    "Please review the evidence."
)


def test_guard_accepts_note_using_only_payload_amounts(seed_states):
    payload = wrong_price_payload(seed_states)
    inv = payload["invoice"]
    text = GOOD.replace("INV-2", inv["invoice_number"]).replace("PO-2", inv["po_id"]).replace("S1", inv["supplier_id"])
    assert notes.guard_errors(text, payload, require_draft=True, min_sentences=3, max_sentences=6) == []


@pytest.mark.parametrize("bad", ["$150.00", "$20.01", "$1,000.00", "$20"])
def test_guard_rejects_amount_not_in_findings(seed_states, bad):
    payload = wrong_price_payload(seed_states)
    text = GOOD.replace("$20.00", bad)
    errors = notes.guard_errors(text, payload, require_draft=True, min_sentences=3, max_sentences=6)
    assert errors and any("not in the verified findings" in e for e in errors)


def test_guard_rejects_unknown_bare_number_and_missing_draft_prefix_and_fraud_wording(seed_states):
    payload = wrong_price_payload(seed_states)
    args = dict(require_draft=True, min_sentences=3, max_sentences=6)
    assert notes.guard_errors(GOOD + " That is 37 percent.", payload, **args)
    assert notes.guard_errors(GOOD.replace("DRAFT — ", ""), payload, **args)
    assert notes.guard_errors(GOOD + " This looks like fraud.", payload, **args)
    assert notes.guard_errors("DRAFT — Too short.", payload, **args)


def test_guard_failure_is_recorded_not_hidden(seed_states, tmp_path):
    states, _, _ = seed_states
    payload = notes.findings_payload(states["wrong-price"])
    cache_mod.write_text_entry(
        "note", payload_json=notes.canonical_json(payload), prompt_version="note-v1", model="m",
        text=GOOD.replace("$20.00", "$150.00"), cache_dir=tmp_path,
    )
    note = notes.draft_note(states["wrong-price"], mode="replay", model="m", cache_dir=tmp_path)
    assert note["source"] == "cached" and note["guard_passed"] is False
    assert "$150.00" in note["text"] and note["guard_errors"]


# --- notes only for non-reconciled invoices -----------------------------------------------------------------------

def test_notes_only_for_discrepant_unresolved_duplicate(seed_states):
    states, _, _ = seed_states
    assert states["clean"].reconciliation.status == "reconciled" and states["clean"].note is None
    for file_id, status in (("wrong-price", "discrepant"), ("duplicate", "duplicate"), ("missing-reference", "unresolved")):
        assert states[file_id].reconciliation.status == status
        note = states[file_id].note
        assert note is not None and note["guard_passed"], (file_id, note)
        assert note["text"].startswith("DRAFT — ")
        assert note["source"] == "simulated"  # no cached note exists in replay; template is labelled, not live
    # persisted state carries the note and provenance
    saved = storage.load_invoice("wrong-price", seed_states[2])
    assert saved.note["source"] == "simulated" and saved.note["guard_passed"] is True


def test_no_note_for_invalid_or_failed_extraction():
    ext = ExtractionResult(status="failed", error="x")
    for status in ("extraction_failed", "invalid", "reconciled"):
        state = InvoiceState(
            file_id="f", image_path="p", ingest_seq=1, ingested_at="t", extraction=ext,
            reconciliation=Reconciliation(status=status),
        )
        assert notes.draft_note(state) is None


def test_template_note_for_wrong_price_has_the_domain_amounts(seed_states):
    states, _, _ = seed_states
    text = states["wrong-price"].note["text"]
    # domain.md / expected-seed-results.json: expected 100.00, billed 120.00, difference 20.00
    for amount in ("$100.00", "$120.00", "$20.00"):
        assert amount in text
    assert "fraud" not in text.lower()


def test_unresolved_note_states_no_expected_amount(seed_states):
    states, _, _ = seed_states
    text = states["missing-reference"].note["text"]
    assert "No expected amount was calculated" in text
    assert states["duplicate"].note["text"].count("clean") == 1  # names the earlier processed document


# --- provenance and replay -----------------------------------------------------------------------------------

def test_replay_never_calls_a_model_and_labels_template_simulated(seed_states, tmp_path):
    states, _, _ = seed_states
    note = notes.draft_note(states["wrong-price"], mode="replay", model="m", provider=ExplodingProvider(), cache_dir=tmp_path)
    assert note["source"] == "simulated" and note["basis"] == "deterministic template" and note["guard_passed"]


def test_live_call_is_cached_then_replayed_as_cached(seed_states, tmp_path):
    states, _, _ = seed_states
    provider = FixedProvider(
        "DRAFT — Invoice INV-2 for supplier S1 and PO PO-2 differs from the order. "
        "It was billed $120.00 and $100.00 was expected, a difference of $20.00. "
        "Please review line 1."
    )
    first = notes.draft_note(states["wrong-price"], mode="live", model="m", provider=provider, cache_dir=tmp_path)
    assert first["source"] == "live" and first["guard_passed"] and provider.calls == 1
    again = notes.draft_note(states["wrong-price"], mode="replay", model="m", provider=ExplodingProvider(), cache_dir=tmp_path)
    assert again["source"] == "cached" and again["text"] == first["text"] and again["cache_key"] == first["cache_key"]


def test_provider_error_falls_back_to_template_and_does_not_raise(seed_states, tmp_path):
    class Failing:
        def generate_text(self, prompt, model):
            raise RuntimeError("quota")

    states, _, _ = seed_states
    note = notes.draft_note(states["wrong-price"], mode="live", model="m", provider=Failing(), cache_dir=tmp_path)
    assert note["source"] == "simulated" and "quota" in note["error"] and note["guard_passed"]


def test_correction_to_reconciled_removes_the_note(seed_states):
    _, _, tmp_path = seed_states
    for field, value in (("lines[0].unit_price", "20.00"), ("lines[0].line_total", "100.00"), ("invoice_total", "100.00")):
        pipeline.add_correction("wrong-price", field, value, "check", state_dir=tmp_path, reference_paths=REFS)
    assert storage.load_invoice("wrong-price", tmp_path).note is None


# --- insight -------------------------------------------------------------------------------------------------

def make_state(file_id, supplier, findings, lines):
    return InvoiceState(
        file_id=file_id, image_path="p", ingest_seq=1, ingested_at="t",
        extraction=ExtractionResult(status="ok"),
        normalized=NormalizedInvoice(invoice_number=file_id, supplier_id=supplier, po_id="PO-X"),
        reconciliation=Reconciliation(status="discrepant", findings=findings, lines=lines),
    )


def synthetic_states():
    line = lambda sku: [LineResult(line_no=1, sku=sku)]  # noqa: E731
    return {
        "a": make_state("a", "S1", [Finding(code="price_diff", line_no=1)], line("K1")),
        "b": make_state("b", "S1", [Finding(code="price_diff", line_no=1), Finding(code="qty_over_ordered", line_no=1)], line("K1")),
        "c": make_state("c", "S2", [Finding(code="price_diff", line_no=1)], line("K2")),
    }


def test_aggregate_counts_and_strongest_observation_by_hand():
    agg = insights.aggregate(synthetic_states())
    assert agg["by_code"] == {"price_diff": 3, "qty_over_ordered": 1}
    assert agg["invoices_by_code"] == {"price_diff": 3, "qty_over_ordered": 1}
    assert agg["supplier_by_code"]["price_diff"] == {"S1": 2, "S2": 1}
    assert agg["sku_by_code"]["price_diff"] == {"K1": 2, "K2": 1}
    summary = BatchSummary(counts={"discrepant": 3}, recoverable_cents=2000, net_difference_cents=2000)
    payload = insights.insight_payload(agg, summary)
    assert payload["finding_code"] == "price_diff" and payload["occurrences"] == 3
    assert payload["top_supplier"] == {"supplier_id": "S1", "occurrences": 2}
    assert payload["top_sku"] == {"sku": "K1", "occurrences": 2}
    assert payload["batch"]["recoverable_total"] == "$20.00"


def test_insight_fallback_is_labelled_and_passes_guard(tmp_path):
    summary = BatchSummary(counts={"discrepant": 3}, recoverable_cents=2000, net_difference_cents=2000)
    result = insights.make_insight(synthetic_states(), summary, mode="replay", model="m", provider=ExplodingProvider(), cache_dir=tmp_path)
    assert result["source"] == "simulated" and result["guard_passed"]
    assert "count: 3" in result["text"] and "Supplier most often involved: S1" in result["text"]


def test_insight_guard_rejects_invented_amount(tmp_path):
    summary = BatchSummary(counts={"discrepant": 3}, recoverable_cents=2000, net_difference_cents=2000)
    payload = insights.insight_payload(insights.aggregate(synthetic_states()), summary)
    cache_mod.write_text_entry(
        "insight", payload_json=notes.canonical_json(payload), prompt_version="insight-v1", model="m",
        text="Price differences are most frequent. Recoverable amounts total $99.00.", cache_dir=tmp_path,
    )
    result = insights.make_insight(synthetic_states(), summary, mode="replay", model="m", cache_dir=tmp_path)
    assert result["source"] == "cached" and result["guard_passed"] is False


def test_insight_without_findings_is_plain_text():
    result = insights.make_insight({}, BatchSummary(counts={}, recoverable_cents=0, net_difference_cents=0))
    assert result["source"] == "simulated" and result["guard_passed"] and result["payload"] is None


def test_pipeline_saves_insight(seed_states):
    _, _, tmp_path = seed_states
    insight = storage.load_insight(tmp_path)
    assert insight["source"] == "simulated" and insight["guard_passed"]
