"""Read/write saved model responses in data/model_cache/extract/. Key = sha256(image + prompt version + model)."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from invoice_recon import config


class CacheError(Exception):
    pass


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cache_key(image_bytes: bytes, prompt_version: str, model: str) -> str:
    return sha256_hex(image_bytes + prompt_version.encode("utf-8") + model.encode("utf-8"))


def _extract_dir(cache_dir: Path | None) -> Path:
    return (cache_dir or config.MODEL_CACHE_DIR) / "extract"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CacheError(f"Unreadable cache entry {path.name}: {exc}") from exc


def read_entry(
    image_bytes: bytes, prompt_version: str, model: str, cache_dir: Path | None = None
) -> dict | None:
    """Return the cache entry or None on a miss.

    With a model, the exact key is used. With an empty model (replay without GEMINI_MODEL), entries are found by
    image hash + prompt version; more than one model for the same image is ambiguous and raises CacheError.
    """
    directory = _extract_dir(cache_dir)
    if model:
        path = directory / f"{cache_key(image_bytes, prompt_version, model)}.json"
        return _load(path) if path.is_file() else None
    if not directory.is_dir():
        return None
    image_hash = sha256_hex(image_bytes)
    found = []
    for path in sorted(directory.glob("*.json")):
        entry = _load(path)
        if entry.get("image_sha256") == image_hash and entry.get("prompt_version") == prompt_version:
            found.append(entry)
    if len(found) > 1:
        raise CacheError("Several cached models exist for this image; set GEMINI_MODEL to choose one")
    return found[0] if found else None


def write_entry(
    *,
    image_bytes: bytes,
    prompt_version: str,
    model: str,
    file_id: str,
    raw_text: str,
    parsed: dict,
    cache_dir: Path | None = None,
) -> str:
    """Write a cache entry atomically and return its key."""
    key = cache_key(image_bytes, prompt_version, model)
    directory = _extract_dir(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    entry = {
        "cache_key": key,
        "provider": "gemini",
        "model": model,
        "prompt_version": prompt_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "image_sha256": sha256_hex(image_bytes),
        "file_id": file_id,
        "raw_text": raw_text,
        "parsed": parsed,
    }
    path = directory / f"{key}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return key


# Text responses (notes, insights): data/model_cache/<kind>/<key>.json, key = sha256(payload + prompt version + model).
def text_cache_key(payload_json: str, prompt_version: str, model: str) -> str:
    return sha256_hex(payload_json.encode("utf-8") + prompt_version.encode("utf-8") + model.encode("utf-8"))


def read_text_entry(
    kind: str, payload_json: str, prompt_version: str, model: str, cache_dir: Path | None = None
) -> dict | None:
    """Cache entry for a findings payload or None on a miss. An empty model matches by payload hash + prompt."""
    directory = (cache_dir or config.MODEL_CACHE_DIR) / kind
    if model:
        path = directory / f"{text_cache_key(payload_json, prompt_version, model)}.json"
        return _load(path) if path.is_file() else None
    if not directory.is_dir():
        return None
    payload_hash = sha256_hex(payload_json.encode("utf-8"))
    found = []
    for path in sorted(directory.glob("*.json")):
        entry = _load(path)
        if entry.get("payload_sha256") == payload_hash and entry.get("prompt_version") == prompt_version:
            found.append(entry)
    if len(found) > 1:
        raise CacheError("Several cached models exist for this payload; set GEMINI_MODEL to choose one")
    return found[0] if found else None


def write_text_entry(
    kind: str, *, payload_json: str, prompt_version: str, model: str, text: str, cache_dir: Path | None = None
) -> str:
    key = text_cache_key(payload_json, prompt_version, model)
    directory = (cache_dir or config.MODEL_CACHE_DIR) / kind
    directory.mkdir(parents=True, exist_ok=True)
    entry = {
        "cache_key": key,
        "provider": "gemini",
        "model": model,
        "prompt_version": prompt_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payload_sha256": sha256_hex(payload_json.encode("utf-8")),
        "payload": json.loads(payload_json),
        "text": text,
    }
    path = directory / f"{key}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return key
