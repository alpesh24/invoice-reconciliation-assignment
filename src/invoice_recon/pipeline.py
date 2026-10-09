"""Orchestration: discover -> extract (cached) -> normalize (+corrections) -> reconcile whole batch -> save.

Extraction is the only step that may call a model; `reconcile_all` and `add_correction` never do.
"""

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from invoice_recon import config, insights, notes, storage
from invoice_recon.documents import Document, discover_documents, relative_image_path
from invoice_recon.extraction.base import ExtractionResult
from invoice_recon.extraction.service import extract_document
from invoice_recon.models import BatchItem, BatchSummary, Correction, NormalizedInvoice, RawExtraction
from invoice_recon.normalize import apply_corrections, effective_normalized, get_raw_value
from invoice_recon.reconcile import reconcile_batch
from invoice_recon.reference import load_reference
from invoice_recon.storage import InvoiceState, ReviewState

Extractor = Callable[[str, Path], ExtractionResult]
REVIEW_STATUSES = ("pending", "in_review", "done")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_reference_paths() -> list[Path]:
    # Reference data is only purchase orders and receipts (rule 6); the loader ignores everything else.
    return [config.INPUTS_DIR / "seed.json", config.GENERATED_DIR / "reference.json"]


def default_extractor() -> Extractor:
    provider = None
    if config.MODEL_MODE == "live" and config.GEMINI_API_KEY:
        try:
            from invoice_recon.extraction.gemini import GeminiProvider

            provider = GeminiProvider(config.GEMINI_API_KEY)
        except Exception:  # missing package or bad setup: extraction reports a clear per-document failure
            provider = None
    return lambda file_id, path: extract_document(file_id, path, provider=provider)


def _normalize_state(state: InvoiceState) -> NormalizedInvoice | None:
    """Normalized invoice from the immutable raw extraction plus the correction overlay."""
    ext = state.extraction
    if ext.status != "ok" or ext.raw is None:
        return None
    try:
        return effective_normalized(ext.raw, state.corrections)
    except ValueError as exc:  # a saved correction no longer applies; rule 9: show it, do not crash the batch
        return NormalizedInvoice(errors={"corrections": f"cannot apply saved corrections: {exc}"})


def recompute(states: dict[str, InvoiceState], reference_paths: list[Path] | None = None) -> BatchSummary:
    """Re-normalize and reconcile the whole batch in place. Pure with respect to disk (reads reference only)."""
    orders, receipts = load_reference(reference_paths if reference_paths is not None else default_reference_paths())
    items = []
    for state in states.values():
        state.normalized = _normalize_state(state)
        ok = state.extraction.status == "ok"
        items.append(
            BatchItem(
                file_id=state.file_id,
                ingest_seq=state.ingest_seq,
                extraction_ok=ok,
                extraction_error=state.extraction.error,
                normalized=state.normalized,
            )
        )
    results, summary = reconcile_batch(items, orders, receipts)
    for file_id, result in results.items():
        states[file_id].reconciliation = result
    return summary


def default_note_provider() -> notes.TextProvider | None:
    """Live text provider, only in live mode with a key; otherwise None (cache, then labelled template)."""
    if config.MODEL_MODE == "live" and config.GEMINI_API_KEY:
        try:
            from invoice_recon.extraction.gemini import GeminiProvider

            return GeminiProvider(config.GEMINI_API_KEY)
        except Exception:
            return None
    return None


def attach_notes(
    states: dict[str, InvoiceState], summary: BatchSummary, provider: notes.TextProvider | None = None
) -> dict:
    """Draft notes (discrepant/unresolved/duplicate only) and the batch insight. Only a provider can call a model."""
    for state in states.values():
        state.note = notes.draft_note(state, provider=provider)
    return insights.make_insight(states, summary, provider=provider)


def _save_all(
    states: dict[str, InvoiceState],
    summary: BatchSummary,
    state_dir: Path | None,
    provider: notes.TextProvider | None = None,
) -> None:
    insight = attach_notes(states, summary, provider)
    for state in states.values():
        storage.save_invoice(state, state_dir)
    storage.save_summary(summary, state_dir)
    storage.save_insight(insight, state_dir)


def run_pipeline(
    *,
    documents: list[Document] | None = None,
    state_dir: Path | None = None,
    reference_paths: list[Path] | None = None,
    extractor: Extractor | None = None,
    note_provider: notes.TextProvider | None = None,
    now: Callable[[], str] = utc_now,
) -> tuple[dict[str, InvoiceState], BatchSummary]:
    """Process all documents. New ones get a persistent ingest_seq; known ones keep seq, corrections, review.

    A successful saved extraction is kept as is (the original is immutable); a failed one is retried.
    """
    documents = documents if documents is not None else discover_documents()
    extract = extractor or default_extractor()
    states = storage.load_all(state_dir)
    next_seq = max((s.ingest_seq for s in states.values()), default=0) + 1

    for doc in documents:
        state = states.get(doc.file_id)
        if state is None:
            state = InvoiceState(
                file_id=doc.file_id,
                image_path=relative_image_path(doc.path),
                ingest_seq=next_seq,
                ingested_at=now(),
                extraction=ExtractionResult(status="failed", error="not extracted yet"),
            )
            next_seq += 1
            states[doc.file_id] = state
        elif state.extraction.status == "ok":
            continue
        try:
            state.extraction = extract(doc.file_id, doc.path)
        except Exception as exc:  # extract_document should not raise; rule 9 holds even if it does
            state.extraction = ExtractionResult(
                status="failed", error=f"Unexpected extraction error: {type(exc).__name__}: {exc}"
            )
        storage.save_invoice(state, state_dir)  # persist ingest order as soon as a document is processed

    summary = recompute(states, reference_paths)
    _save_all(states, summary, state_dir, note_provider if note_provider is not None else default_note_provider())
    return states, summary


def reconcile_all(
    *, state_dir: Path | None = None, reference_paths: list[Path] | None = None
) -> tuple[dict[str, InvoiceState], BatchSummary]:
    """Recompute everything from saved extractions and corrections. No model calls."""
    states = storage.load_all(state_dir)
    summary = recompute(states, reference_paths)
    _save_all(states, summary, state_dir)
    return states, summary


def add_correction(
    file_id: str,
    field: str,
    corrected: str | None,
    reason: str,
    *,
    state_dir: Path | None = None,
    reference_paths: list[Path] | None = None,
    now: Callable[[], str] = utc_now,
) -> tuple[dict[str, InvoiceState], BatchSummary]:
    """Append a correction, re-normalize, reconcile the whole batch and save. Invalid targets raise ValueError."""
    states = storage.load_all(state_dir)
    state = states.get(file_id)
    if state is None:
        raise ValueError(f"unknown document {file_id!r}")
    raw: RawExtraction | None = state.extraction.raw
    if state.extraction.status != "ok" or raw is None:
        raise ValueError(f"{file_id} has no extraction to correct")
    original = get_raw_value(raw, field)  # validates the field against the immutable original
    correction = Correction(field=field, original=original, corrected=corrected, reason=reason, at=now())
    apply_corrections(raw, [*state.corrections, correction])  # reject unusable corrections before saving
    state.corrections.append(correction)
    summary = recompute(states, reference_paths)
    _save_all(states, summary, state_dir)
    return states, summary


def update_review(
    file_id: str,
    status: str,
    comment: str,
    *,
    state_dir: Path | None = None,
    now: Callable[[], str] = utc_now,
) -> InvoiceState:
    if status not in REVIEW_STATUSES:
        raise ValueError(f"review status must be one of {REVIEW_STATUSES}")
    state = storage.load_invoice(file_id, state_dir)
    if state is None:
        raise ValueError(f"unknown document {file_id!r}")
    state.review = ReviewState(status=status, comment=comment, updated_at=now())
    storage.save_invoice(state, state_dir)
    return state
