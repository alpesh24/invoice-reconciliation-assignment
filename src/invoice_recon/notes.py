"""Draft notes from verified findings, with a number guard.

The model only phrases. The payload is built from reconcile results; every amount in the text must come from it.
Replay never calls a model: a cache miss falls back to a deterministic template labelled `simulated`.
"""

import json
import re
from pathlib import Path
from typing import Protocol

from invoice_recon import config
from invoice_recon.extraction import cache as cache_mod
from invoice_recon.money import format_cents
from invoice_recon.storage import InvoiceState
from invoice_recon.view import FINDING_LABELS

NOTE_STATUSES = ("discrepant", "unresolved", "duplicate")
DRAFT_PREFIX = "DRAFT — "
# Rule 12: a discrepancy is a difference to review. Wording that implies wrongdoing makes the guard fail.
FORBIDDEN_WORDS = (
    "fraud", "theft", "steal", "stole", "scam", "cheat", "dishonest",
    "deliberate", "intentional", "misconduct", "wrongdoing", "criminal", "illegal",
)
_NUMBER_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_MONEY_RE = re.compile(r"\$\s?(\d+(?:,\d{3})*(?:\.\d+)?)")


class TextProvider(Protocol):
    def generate_text(self, prompt: str, model: str) -> str: ...


def _norm(token: str) -> str:
    return token.replace(",", "")


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def guard_errors(
    text: str, payload: dict, *, require_draft: bool, min_sentences: int, max_sentences: int
) -> list[str]:
    """Reasons the text is not acceptable; an empty list means the guard passed.

    Every `$X.XX` amount must appear as an amount in the payload; every other number must appear somewhere in it.
    """
    errors: list[str] = []
    body = text.strip()
    if not body:
        return ["empty text"]
    if require_draft and not body.startswith(DRAFT_PREFIX):
        errors.append(f"note must start with {DRAFT_PREFIX!r}")
    payload_text = canonical_json(payload)
    allowed_amounts = {_norm(m) for m in _MONEY_RE.findall(payload_text)}
    allowed_numbers = {_norm(m) for m in _NUMBER_RE.findall(payload_text)}
    for raw in _MONEY_RE.findall(body):
        if not re.fullmatch(r"\d+(?:,\d{3})*\.\d{2}", raw) or _norm(raw) not in allowed_amounts:
            errors.append(f"amount ${raw} is not in the verified findings")
    without_money = _MONEY_RE.sub(" ", body)
    for raw in _NUMBER_RE.findall(without_money):
        if _norm(raw) not in allowed_numbers:
            errors.append(f"number {raw} is not in the verified findings")
    lowered = body.lower()
    for word in FORBIDDEN_WORDS:
        if re.search(rf"\b{word}", lowered):
            errors.append(f"wording implies wrongdoing: {word!r}")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
    if not min_sentences <= len(sentences) <= max_sentences:
        errors.append(f"expected {min_sentences}-{max_sentences} sentences, found {len(sentences)}")
    return errors


def _money(cents: int | None) -> str | None:
    return None if cents is None else format_cents(cents)


def _detail(detail: dict) -> dict:
    out = {}
    for key, value in detail.items():
        if key.endswith("_cents") and isinstance(value, int):
            out[key[: -len("_cents")]] = format_cents(value)
        else:
            out[key] = value
    return out


def findings_payload(state: InvoiceState) -> dict | None:
    """Verified findings for a note, or None if this invoice gets no note (reconciled, invalid, failed)."""
    rec, inv = state.reconciliation, state.normalized
    if rec is None or rec.status not in NOTE_STATUSES:
        return None
    return {
        "invoice": {
            "file_id": state.file_id,
            "invoice_number": inv.invoice_number if inv else None,
            "supplier_id": inv.supplier_id if inv else None,
            "po_id": rec.po_id or (inv.po_id if inv else None),
            "status": rec.status,
        },
        "expected": _money(rec.expected_cents),
        "billed": _money(rec.billed_cents),
        "difference": _money(rec.difference_cents),
        "duplicate_of": rec.duplicate_of,
        "lines": [
            {
                "line_no": ln.line_no,
                "sku": ln.sku,
                "ordered_qty": ln.ordered_qty,
                "received_qty": ln.received_qty,
                "billed_qty": ln.billed_qty,
                "agreed_unit": _money(ln.agreed_unit_cents),
                "billed_unit": _money(ln.billed_unit_cents),
                "expected": _money(ln.expected_cents),
                "billed": _money(ln.billed_cents),
                "difference": _money(ln.difference_cents),
            }
            for ln in rec.lines
        ],
        "findings": [
            {
                "code": f.code,
                "meaning": FINDING_LABELS.get(f.code, f.code),
                "line_no": f.line_no,
                "detail": _detail(f.detail),
            }
            for f in rec.findings
        ],
    }


def template_note(payload: dict) -> str:
    """Deterministic fallback wording. Uses only values from the payload, so it passes the guard."""
    inv = payload["invoice"]
    who = f"Invoice {inv['invoice_number']} (supplier {inv['supplier_id']}, PO {inv['po_id']})"
    if inv["status"] == "duplicate":
        return (
            f"{DRAFT_PREFIX}{who} has the same supplier and invoice number as the earlier processed "
            f"document {payload['duplicate_of']}. "
            "It is not counted as payable in the batch totals. "
            "Please compare it with the earlier document to confirm."
        )
    parts = []
    for f in payload["findings"]:
        where = f" (line {f['line_no']})" if f["line_no"] is not None else ""
        parts.append(f"{f['meaning']}{where}")
    listed = "; ".join(parts) if parts else "no individual finding recorded"
    if inv["status"] == "unresolved":
        billed = f" The invoice total is {payload['billed']}." if payload["billed"] else ""
        return (
            f"{DRAFT_PREFIX}{who} could not be matched against the purchase order and receipt data. "
            f"Reasons: {listed}.{billed} "
            "No expected amount was calculated, so no difference is shown. "
            "Please review the evidence and correct the extracted fields if needed."
        )
    return (
        f"{DRAFT_PREFIX}{who} differs from the matched purchase order and needs review. "
        f"The invoice total is {payload['billed']} against an expected {payload['expected']}, "
        f"a difference of {payload['difference']}. "
        f"Findings: {listed}. "
        "These are differences for a reviewer to confirm; no conclusion has been drawn."
    )


def resolve_text(
    *,
    kind: str,
    payload: dict,
    prompt_version: str,
    template: str,
    guard_args: dict,
    mode: str | None = None,
    model: str | None = None,
    provider: TextProvider | None = None,
    cache_dir: Path | None = None,
) -> dict:
    """Cache -> live call (live mode only) -> labelled template. Never raises; the guard result is always recorded."""
    mode = mode or config.MODEL_MODE
    model = config.GEMINI_MODEL if model is None else model
    payload_json = canonical_json(payload)
    text, source, basis, key, used_model, error = None, "simulated", "deterministic template", None, model, None

    try:
        entry = cache_mod.read_text_entry(kind, payload_json, prompt_version, model, cache_dir)
        if entry is not None and isinstance(entry.get("text"), str):
            text, source, basis = entry["text"], "cached", "saved model response"
            key, used_model = entry.get("cache_key"), entry.get("model", model)
        elif mode == "live" and provider is not None and model:
            prompt = (config.PROMPTS_DIR / f"{prompt_version}.md").read_text(encoding="utf-8")
            reply = provider.generate_text(f"{prompt}\nVerified findings JSON:\n{payload_json}\n", model)
            key = cache_mod.write_text_entry(
                kind, payload_json=payload_json, prompt_version=prompt_version, model=model,
                text=reply, cache_dir=cache_dir,
            )
            text, source, basis = reply, "live", "model response"
        elif mode == "live":
            error = "Live mode needs GEMINI_API_KEY and GEMINI_MODEL; template used"
        else:
            error = f"No cached model response ({prompt_version}); replay makes no model calls; template used"
    except Exception as exc:  # rule 9: a failed note never stops the batch
        text, source, basis, key = None, "simulated", "deterministic template", None
        error = f"{type(exc).__name__}: {exc}; template used"

    if text is None:
        text = template
    errors = guard_errors(text, payload, **guard_args)
    return {
        "text": text,
        "source": source,
        "basis": basis,
        "guard_passed": not errors,
        "guard_errors": errors,
        "prompt_version": prompt_version,
        "model": used_model,
        "cache_key": key,
        "error": error,
    }


def draft_note(
    state: InvoiceState,
    *,
    mode: str | None = None,
    model: str | None = None,
    provider: TextProvider | None = None,
    cache_dir: Path | None = None,
) -> dict | None:
    """Guarded draft note for a discrepant, unresolved or duplicate invoice; None for any other status."""
    payload = findings_payload(state)
    if payload is None:
        return None
    return resolve_text(
        kind="note",
        payload=payload,
        prompt_version=config.NOTE_PROMPT_VERSION,
        template=template_note(payload),
        guard_args={"require_draft": True, "min_sentences": 3, "max_sentences": 6},
        mode=mode, model=model, provider=provider, cache_dir=cache_dir,
    )
