"""Atomic JSON read/write of data/state/. All state I/O goes through this module."""

import json
import os
import shutil
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from invoice_recon import config
from invoice_recon.extraction.base import ExtractionResult
from invoice_recon.models import BatchSummary, Correction, NormalizedInvoice, Reconciliation


class StorageError(Exception):
    pass


class ReviewState(BaseModel):
    status: str = "pending"  # pending | in_review | done
    comment: str = ""
    updated_at: str = ""


class InvoiceState(BaseModel):
    file_id: str
    image_path: str
    ingest_seq: int
    ingested_at: str
    extraction: ExtractionResult
    corrections: list[Correction] = Field(default_factory=list)
    normalized: NormalizedInvoice | None = None
    reconciliation: Reconciliation | None = None
    note: dict | None = None  # draft note: text, source, basis, guard_passed, guard_errors (notes.py)
    review: ReviewState = Field(default_factory=ReviewState)


def _state_dir(state_dir: Path | None) -> Path:
    return state_dir if state_dir is not None else config.STATE_DIR


def write_json_atomic(path: Path, data: object) -> None:
    """Write `<file>.tmp` then os.replace, so a reader never sees a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def invoice_path(file_id: str, state_dir: Path | None = None) -> Path:
    return _state_dir(state_dir) / "invoices" / f"{file_id}.json"


def save_invoice(state: InvoiceState, state_dir: Path | None = None) -> None:
    write_json_atomic(invoice_path(state.file_id, state_dir), json.loads(state.model_dump_json()))


def load_invoice(file_id: str, state_dir: Path | None = None) -> InvoiceState | None:
    path = invoice_path(file_id, state_dir)
    if not path.is_file():
        return None
    try:
        return InvoiceState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as exc:
        raise StorageError(f"Unreadable state file {path}: {exc}") from exc


def load_all(state_dir: Path | None = None) -> dict[str, InvoiceState]:
    folder = _state_dir(state_dir) / "invoices"
    if not folder.is_dir():
        return {}
    states = {}
    for path in sorted(folder.glob("*.json")):
        state = load_invoice(path.stem, state_dir)
        if state is not None:
            states[state.file_id] = state
    return states


def load_all_tolerant(state_dir: Path | None = None) -> tuple[dict[str, InvoiceState], dict[str, str]]:
    """Like load_all, but an unreadable state file becomes an entry in the error map (file_id -> reason).

    For read-only views (the UI). The pipeline keeps using load_all: re-creating a corrupt document as new
    would silently drop its ingest order, corrections and review state.
    """
    folder = _state_dir(state_dir) / "invoices"
    if not folder.is_dir():
        return {}, {}
    states: dict[str, InvoiceState] = {}
    errors: dict[str, str] = {}
    for path in sorted(folder.glob("*.json")):
        try:
            state = load_invoice(path.stem, state_dir)
        except StorageError as exc:
            errors[path.stem] = str(exc)
            continue
        if state is not None:
            states[state.file_id] = state
    return states, errors


def save_summary(summary: BatchSummary, state_dir: Path | None = None) -> None:
    write_json_atomic(_state_dir(state_dir) / "summary.json", json.loads(summary.model_dump_json()))


def load_summary(state_dir: Path | None = None) -> BatchSummary | None:
    path = _state_dir(state_dir) / "summary.json"
    if not path.is_file():
        return None
    try:
        return BatchSummary.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as exc:
        raise StorageError(f"Unreadable summary file {path}: {exc}") from exc


def save_insight(insight: dict, state_dir: Path | None = None) -> None:
    write_json_atomic(_state_dir(state_dir) / "insight.json", insight)


def load_insight(state_dir: Path | None = None) -> dict | None:
    path = _state_dir(state_dir) / "insight.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StorageError(f"Unreadable insight file {path}: {exc}") from exc


def reset_state(state_dir: Path | None = None) -> bool:
    """Delete the state directory (never the model cache). Returns True if something was deleted."""
    target = _state_dir(state_dir)
    if not target.exists():
        return False
    shutil.rmtree(target)
    return True
