"""Extraction result model and provider protocol."""

from typing import Literal, Optional, Protocol

from pydantic import BaseModel

from invoice_recon.models import RawExtraction

Source = Literal["live", "cached", "simulated"]


class ExtractionResult(BaseModel):
    """Outcome of extracting one document. `source` labels provenance (never present simulated as real)."""

    status: Literal["ok", "failed"]
    source: Source | None = None
    provider: str = "gemini"
    model: str = ""
    prompt_version: str = ""
    cache_key: str | None = None
    error: str | None = None
    raw: RawExtraction | None = None
    # When a simulation replaced the result, the real (cached/live) result for the same image is kept here.
    underlying: Optional["ExtractionResult"] = None


class ExtractionProvider(Protocol):
    """A live model client: image bytes in, raw response text out. Raises on any failure."""

    def generate(self, image_bytes: bytes, mime_type: str, prompt: str, model: str) -> str: ...
