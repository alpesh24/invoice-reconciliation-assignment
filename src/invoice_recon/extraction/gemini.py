"""Live Gemini provider. The google-genai import is lazy so replay mode needs neither the package nor a key."""

import time

from invoice_recon import config
from invoice_recon.models import RawExtraction

TRANSIENT_CODES = {429, 500, 502, 503, 504}


def build_generate_config():
    """Generation settings: temperature 0, JSON output, RawExtraction schema, fixed output limit and timeout."""
    from google.genai import types

    return types.GenerateContentConfig(
        temperature=config.GEMINI_TEMPERATURE,
        response_mime_type="application/json",
        response_schema=RawExtraction,
        max_output_tokens=config.GEMINI_MAX_OUTPUT_TOKENS,
        http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_SECONDS * 1000),
    )


def _is_transient(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code in TRANSIENT_CODES
    return isinstance(exc, (TimeoutError, ConnectionError))


class GeminiProvider:
    def __init__(self, api_key: str, *, retries: int | None = None, backoff_seconds: float = 2.0):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._retries = config.GEMINI_MAX_RETRIES if retries is None else retries
        self._backoff = backoff_seconds

    def generate(self, image_bytes: bytes, mime_type: str, prompt: str, model: str) -> str:
        from google.genai import types

        contents = [types.Part.from_bytes(data=image_bytes, mime_type=mime_type), prompt]
        settings = build_generate_config()
        for attempt in range(self._retries + 1):
            try:
                response = self._client.models.generate_content(model=model, contents=contents, config=settings)
                text = response.text
                if not text:
                    raise ValueError("Empty model response")
                return text
            except Exception as exc:  # retry transient errors only; re-raise everything else
                if attempt < self._retries and _is_transient(exc):
                    time.sleep(self._backoff * (2**attempt))
                    continue
                raise
        raise RuntimeError("unreachable")

    def generate_text(self, prompt: str, model: str) -> str:
        """Plain-text generation for notes and insights (temperature 0, fixed output limit, no schema)."""
        from google.genai import types

        settings = types.GenerateContentConfig(
            temperature=config.GEMINI_TEMPERATURE,
            max_output_tokens=config.GEMINI_MAX_OUTPUT_TOKENS,
            http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_SECONDS * 1000),
        )
        for attempt in range(self._retries + 1):
            try:
                response = self._client.models.generate_content(model=model, contents=[prompt], config=settings)
                text = response.text
                if not text:
                    raise ValueError("Empty model response")
                return text.strip()
            except Exception as exc:
                if attempt < self._retries and _is_transient(exc):
                    time.sleep(self._backoff * (2**attempt))
                    continue
                raise
        raise RuntimeError("unreachable")
