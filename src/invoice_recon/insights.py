"""Batch insight: deterministic aggregates pick the strongest observation; the model only words it.

Fallback text is deterministic and labelled `simulated` (never presented as a model response).
"""

from collections import Counter
from pathlib import Path

from invoice_recon import config
from invoice_recon.models import BatchSummary
from invoice_recon.money import format_cents
from invoice_recon.notes import TextProvider, resolve_text
from invoice_recon.storage import InvoiceState
from invoice_recon.view import FINDING_LABELS


def aggregate(states: dict[str, InvoiceState]) -> dict:
    """Finding counts overall, per supplier and per SKU (counts only; no amounts are attributed to a finding)."""
    by_code: Counter[str] = Counter()
    code_invoices: dict[str, set[str]] = {}
    code_supplier: dict[str, Counter[str]] = {}
    code_sku: dict[str, Counter[str]] = {}
    for state in states.values():
        rec, inv = state.reconciliation, state.normalized
        if rec is None:
            continue
        sku_by_line = {ln.line_no: ln.sku for ln in rec.lines}
        for f in rec.findings:
            by_code[f.code] += 1
            code_invoices.setdefault(f.code, set()).add(state.file_id)
            supplier = inv.supplier_id if inv else None
            if supplier:
                code_supplier.setdefault(f.code, Counter())[supplier] += 1
            sku = sku_by_line.get(f.line_no) if f.line_no is not None else None
            if sku:
                code_sku.setdefault(f.code, Counter())[sku] += 1
    return {
        "by_code": dict(sorted(by_code.items())),
        "invoices_by_code": {c: len(v) for c, v in sorted(code_invoices.items())},
        "supplier_by_code": {c: dict(sorted(v.items())) for c, v in sorted(code_supplier.items())},
        "sku_by_code": {c: dict(sorted(v.items())) for c, v in sorted(code_sku.items())},
    }


def _top(counts: dict[str, int] | None) -> tuple[str, int] | None:
    if not counts:
        return None
    return max(sorted(counts.items()), key=lambda kv: kv[1])  # highest count; ties resolve to the first by name


def insight_payload(agg: dict, summary: BatchSummary) -> dict | None:
    """The strongest observation: the most frequent finding code (ties by name), with its top supplier and SKU."""
    top = _top(agg["by_code"])
    if top is None:
        return None
    code, occurrences = top
    supplier = _top(agg["supplier_by_code"].get(code))
    sku = _top(agg["sku_by_code"].get(code))
    return {
        "finding_code": code,
        "meaning": FINDING_LABELS.get(code, code),
        "occurrences": occurrences,
        "invoices_affected": agg["invoices_by_code"][code],
        "top_supplier": {"supplier_id": supplier[0], "occurrences": supplier[1]} if supplier else None,
        "top_sku": {"sku": sku[0], "occurrences": sku[1]} if sku else None,
        "batch": {
            "discrepant_invoices": summary.counts.get("discrepant", 0),
            "recoverable_total": format_cents(summary.recoverable_cents),
        },
    }


def fallback_text(payload: dict | None) -> str:
    if payload is None:
        return "No findings were recorded in this batch. Nothing stands out for review."
    text = (
        f"The most frequent finding is: {payload['meaning']} "
        f"(count: {payload['occurrences']}, invoices affected: {payload['invoices_affected']})."
    )
    if payload["top_supplier"]:
        s = payload["top_supplier"]
        text += f" Supplier most often involved: {s['supplier_id']} (count: {s['occurrences']})."
    if payload["top_sku"]:
        k = payload["top_sku"]
        text += f" SKU most often involved: {k['sku']} (count: {k['occurrences']})."
    return text


def make_insight(
    states: dict[str, InvoiceState],
    summary: BatchSummary,
    *,
    mode: str | None = None,
    model: str | None = None,
    provider: TextProvider | None = None,
    cache_dir: Path | None = None,
) -> dict:
    """Insight text with provenance and guard result. Without findings the deterministic text is used directly."""
    payload = insight_payload(aggregate(states), summary)
    if payload is None:
        return {
            "text": fallback_text(None), "source": "simulated", "basis": "deterministic template",
            "guard_passed": True, "guard_errors": [], "prompt_version": config.INSIGHT_PROMPT_VERSION,
            "model": "", "cache_key": None, "error": None, "payload": None,
        }
    result = resolve_text(
        kind="insight",
        payload=payload,
        prompt_version=config.INSIGHT_PROMPT_VERSION,
        template=fallback_text(payload),
        guard_args={"require_draft": False, "min_sentences": 1, "max_sentences": 3},
        mode=mode, model=model, provider=provider, cache_dir=cache_dir,
    )
    result["payload"] = payload
    return result
