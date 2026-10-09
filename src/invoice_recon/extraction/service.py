"""Extract one document: simulated failure -> cache -> live call -> validation -> simulation overlay.

Never raises for a per-document problem: every failure becomes a `failed` ExtractionResult (CLAUDE.md rule 9).
"""

import io
import json
from pathlib import Path

from PIL import Image

from invoice_recon import config
from invoice_recon.extraction import cache as cache_mod
from invoice_recon.extraction.base import ExtractionProvider, ExtractionResult
from invoice_recon.extraction.simulated import apply_simulation, load_simulations
from invoice_recon.models import RawExtraction

MIME_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def load_prompt(prompt_version: str | None = None) -> str:
    version = prompt_version or config.EXTRACT_PROMPT_VERSION
    return (config.PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8")


def _fail(error: str, *, source=None, model="", prompt_version="", key=None) -> ExtractionResult:
    return ExtractionResult(
        status="failed", source=source, model=model, prompt_version=prompt_version, cache_key=key, error=error
    )


def _extract_real(
    file_id: str,
    image_path: Path,
    *,
    mode: str,
    model: str,
    provider: ExtractionProvider | None,
    cache_dir: Path | None,
    refresh: bool,
) -> ExtractionResult:
    version = config.EXTRACT_PROMPT_VERSION
    mime = MIME_TYPES.get(image_path.suffix.lower())
    if mime is None:
        return _fail(f"Unsupported image type {image_path.suffix!r}", model=model, prompt_version=version)
    try:
        image_bytes = image_path.read_bytes()
        Image.open(io.BytesIO(image_bytes)).verify()
    except Exception as exc:
        return _fail(f"Unreadable image {image_path.name}: {exc}", model=model, prompt_version=version)

    try:
        entry = None if refresh else cache_mod.read_entry(image_bytes, version, model, cache_dir)
    except cache_mod.CacheError as exc:
        return _fail(str(exc), model=model, prompt_version=version)

    if entry is not None:
        entry_model, key = entry.get("model", model), entry.get("cache_key")
        try:
            raw = RawExtraction.model_validate_json(entry.get("raw_text", ""))
        except ValueError as exc:
            return _fail(
                f"Cached response is not valid RawExtraction JSON: {exc}",
                source="cached", model=entry_model, prompt_version=version, key=key,
            )
        return ExtractionResult(
            status="ok", source="cached", model=entry_model, prompt_version=version, cache_key=key, raw=raw
        )

    if mode != "live":
        return _fail(
            f"No cached model response for {file_id} (prompt {version}); replay mode makes no model calls",
            model=model, prompt_version=version,
        )
    if provider is None or not model:
        return _fail("Live mode needs GEMINI_API_KEY and GEMINI_MODEL", model=model, prompt_version=version)
    try:
        text = provider.generate(image_bytes, mime, load_prompt(version), model)
    except Exception as exc:  # API errors, timeouts, empty responses
        return _fail(f"Model call failed: {type(exc).__name__}: {exc}", model=model, prompt_version=version)
    try:
        raw = RawExtraction.model_validate_json(text)
    except ValueError as exc:
        return _fail(
            f"Model response is not valid RawExtraction JSON: {exc}; response starts: {text[:200]!r}",
            model=model, prompt_version=version,
        )
    key = cache_mod.write_entry(
        image_bytes=image_bytes, prompt_version=version, model=model, file_id=file_id,
        raw_text=text, parsed=json.loads(raw.model_dump_json()), cache_dir=cache_dir,
    )
    return ExtractionResult(status="ok", source="live", model=model, prompt_version=version, cache_key=key, raw=raw)


def extract_document(
    file_id: str,
    image_path: Path,
    *,
    mode: str | None = None,
    model: str | None = None,
    provider: ExtractionProvider | None = None,
    cache_dir: Path | None = None,
    simulations: dict[str, dict] | None = None,
    use_simulations: bool | None = None,
    simulated_failures: frozenset[str] | None = None,
    refresh: bool = False,
) -> ExtractionResult:
    """Extract one document. Live mode uses an existing cache entry unless `refresh`; a miss calls the provider."""
    mode = mode or config.MODEL_MODE
    model = config.GEMINI_MODEL if model is None else model
    failures = config.SIMULATED_FAILURES if simulated_failures is None else simulated_failures
    use_sims = config.USE_SIMULATIONS if use_simulations is None else use_simulations

    if file_id in failures:
        return ExtractionResult(
            status="failed", source="simulated", provider="simulation", model=model,
            prompt_version=config.EXTRACT_PROMPT_VERSION,
            error="Simulated API failure (SIMULATED_FAILURES); no model call was made",
        )
    try:
        real = _extract_real(
            file_id, Path(image_path), mode=mode, model=model, provider=provider,
            cache_dir=cache_dir, refresh=refresh,
        )
        if use_sims:
            sims = load_simulations() if simulations is None else simulations
            simulated = apply_simulation(file_id, real, sims)
            if simulated is not None:
                return simulated
        return real
    except Exception as exc:  # last resort: a batch never stops on one document
        return _fail(
            f"Unexpected extraction error: {type(exc).__name__}: {exc}",
            model=model, prompt_version=config.EXTRACT_PROMPT_VERSION,
        )
