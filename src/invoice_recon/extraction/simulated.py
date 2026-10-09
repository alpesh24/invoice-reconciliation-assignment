"""Simulations from data/simulations.json: replace a raw extraction or force a failure. Always labelled simulated.

Entry format, keyed by file_id:
  {"kind": "replace_raw", "raw": {...RawExtraction...}, "note": "why"}
  {"kind": "fail", "error": "text", "note": "why"}
"""

import json
from pathlib import Path

from invoice_recon import config
from invoice_recon.extraction.base import ExtractionResult
from invoice_recon.models import RawExtraction


def load_simulations(path: Path | None = None) -> dict[str, dict]:
    target = path or config.SIMULATIONS_PATH
    if not target.is_file():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def apply_simulation(
    file_id: str, real: ExtractionResult | None, simulations: dict[str, dict]
) -> ExtractionResult | None:
    """Return the simulated result for file_id (keeping `real` as `underlying`), or None if not simulated."""
    entry = simulations.get(file_id)
    if entry is None:
        return None
    kind = entry.get("kind")
    base = {
        "source": "simulated",
        "provider": "simulation",
        "model": real.model if real else "",
        "prompt_version": real.prompt_version if real else "",
        "underlying": real,
    }
    if kind == "fail":
        return ExtractionResult(status="failed", error=entry.get("error") or "Simulated failure", **base)
    if kind == "replace_raw":
        try:
            raw = RawExtraction.model_validate(entry.get("raw"))
        except ValueError as exc:
            return ExtractionResult(status="failed", error=f"Invalid simulation for {file_id}: {exc}", **base)
        return ExtractionResult(status="ok", raw=raw, **base)
    return ExtractionResult(status="failed", error=f"Unknown simulation kind {kind!r} for {file_id}", **base)
