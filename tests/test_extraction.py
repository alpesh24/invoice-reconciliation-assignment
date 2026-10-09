"""Extraction tests: replay, cache, failures, simulations. No network; the provider is a fake."""

import json
from pathlib import Path

import pytest
from PIL import Image

from invoice_recon import config
from invoice_recon.extraction import cache as cache_mod
from invoice_recon.extraction.service import extract_document
from invoice_recon.models import RawExtraction

MODEL = "test-model"
VERSION = config.EXTRACT_PROMPT_VERSION
RAW = {
    "invoice_number": "INV-2", "supplier_id": "S1", "po_id": "PO-2", "currency": "USD",
    "lines": [{"sku": "CAB-1", "description": None, "quantity": "5", "unit_price": "24.00", "line_total": "120.00"}],
    "invoice_total": "120.00", "warnings": [],
}


class FakeProvider:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text if text is not None else json.dumps(RAW), error, 0

    def generate(self, image_bytes, mime_type, prompt, model):
        self.calls += 1
        if self.error:
            raise self.error
        return self.text


@pytest.fixture
def image(tmp_path) -> Path:
    path = tmp_path / "a.png"
    Image.new("RGB", (20, 20), "white").save(path)
    return path


def run(image, tmp_path, **kw):
    kw.setdefault("model", MODEL)
    kw.setdefault("mode", "replay")
    kw.setdefault("simulations", {})
    kw.setdefault("simulated_failures", frozenset())
    return extract_document(image.stem, image, cache_dir=tmp_path / "cache", **kw)


def put_cache(image, tmp_path, raw_text, model=MODEL):
    return cache_mod.write_entry(
        image_bytes=image.read_bytes(), prompt_version=VERSION, model=model, file_id="a",
        raw_text=raw_text, parsed={}, cache_dir=tmp_path / "cache",
    )


def test_replay_cache_hit(image, tmp_path):
    key = put_cache(image, tmp_path, json.dumps(RAW))
    result = run(image, tmp_path)
    assert result.status == "ok" and result.source == "cached" and result.cache_key == key
    assert result.raw == RawExtraction.model_validate(RAW)


def test_replay_without_model_finds_entry_by_image_hash(image, tmp_path):
    put_cache(image, tmp_path, json.dumps(RAW))
    result = run(image, tmp_path, model="")
    assert result.status == "ok" and result.source == "cached" and result.model == MODEL


def test_replay_without_model_ambiguous_entries_fail(image, tmp_path):
    put_cache(image, tmp_path, json.dumps(RAW), model="m1")
    put_cache(image, tmp_path, json.dumps(RAW), model="m2")
    result = run(image, tmp_path, model="")
    assert result.status == "failed" and "GEMINI_MODEL" in result.error


def test_replay_cache_miss_fails_without_calling_model(image, tmp_path):
    provider = FakeProvider()
    result = run(image, tmp_path, provider=provider)
    assert result.status == "failed" and "No cached model response" in result.error
    assert provider.calls == 0


def test_invalid_json_in_cache_fails(image, tmp_path):
    put_cache(image, tmp_path, "not json {")
    result = run(image, tmp_path)
    assert result.status == "failed" and "not valid RawExtraction JSON" in result.error


def test_live_miss_calls_provider_and_writes_cache_then_replays(image, tmp_path):
    provider = FakeProvider()
    live = run(image, tmp_path, mode="live", provider=provider)
    assert live.status == "ok" and live.source == "live" and provider.calls == 1
    replayed = run(image, tmp_path)
    assert replayed.source == "cached" and replayed.raw == live.raw and replayed.cache_key == live.cache_key
    # live mode with an existing entry makes no new call
    assert run(image, tmp_path, mode="live", provider=provider).source == "cached" and provider.calls == 1


def test_live_invalid_json_fails_and_is_not_cached(image, tmp_path):
    result = run(image, tmp_path, mode="live", provider=FakeProvider(text="oops"))
    assert result.status == "failed" and "not valid RawExtraction JSON" in result.error
    assert not (tmp_path / "cache" / "extract").exists()


def test_live_api_error_fails(image, tmp_path):
    result = run(image, tmp_path, mode="live", provider=FakeProvider(error=RuntimeError("quota")))
    assert result.status == "failed" and "quota" in result.error


def test_live_without_provider_fails(image, tmp_path):
    assert run(image, tmp_path, mode="live").status == "failed"


def test_unreadable_image_fails(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    result = run(bad, tmp_path)
    assert result.status == "failed" and "Unreadable image" in result.error


def test_missing_file_fails(tmp_path):
    assert run(tmp_path / "gone.png", tmp_path).status == "failed"


def test_simulated_failure_does_not_stop_batch(image, tmp_path):
    other = tmp_path / "b.png"
    Image.new("RGB", (20, 20), "black").save(other)
    put_cache(other, tmp_path, json.dumps(RAW))
    results = {
        p.stem: run(p, tmp_path, simulated_failures=frozenset({"a"})) for p in (image, other)
    }
    assert results["a"].status == "failed" and results["a"].source == "simulated"
    assert results["b"].status == "ok" and results["b"].source == "cached"


def test_simulation_replaces_raw_and_keeps_real(image, tmp_path):
    put_cache(image, tmp_path, json.dumps(RAW))
    sim_raw = dict(RAW, po_id="PO-S")
    sims = {"a": {"kind": "replace_raw", "raw": sim_raw}}
    result = run(image, tmp_path, simulations=sims, use_simulations=True)
    assert result.source == "simulated" and result.raw.po_id == "PO-S"
    assert result.underlying.source == "cached" and result.underlying.raw.po_id == "PO-2"
    off = run(image, tmp_path, simulations=sims, use_simulations=False)
    assert off.source == "cached" and off.raw.po_id == "PO-2"


def test_simulation_fail_kind(image, tmp_path):
    sims = {"a": {"kind": "fail", "error": "boom"}}
    result = run(image, tmp_path, simulations=sims, use_simulations=True)
    assert result.status == "failed" and result.source == "simulated" and result.error == "boom"


def test_cache_key_depends_on_image_prompt_and_model():
    base = cache_mod.cache_key(b"x", "p1", "m")
    assert len({base, cache_mod.cache_key(b"y", "p1", "m"), cache_mod.cache_key(b"x", "p2", "m"),
                cache_mod.cache_key(b"x", "p1", "n")}) == 4


def test_gemini_generate_config_settings():
    from invoice_recon.extraction.gemini import build_generate_config

    cfg = build_generate_config()
    assert cfg.temperature == 0 and cfg.response_mime_type == "application/json"
    assert cfg.response_schema is RawExtraction and cfg.max_output_tokens == config.GEMINI_MAX_OUTPUT_TOKENS


def test_extract_prompt_is_real():
    from invoice_recon.extraction.service import load_prompt

    text = load_prompt()
    assert "Placeholder" not in text and "invoice_number" in text and "(missing)" in text
