"""Review UI. Reads and writes only through storage.py / pipeline.py; makes no model calls.

Run with: streamlit run app/streamlit_app.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:  # allow running without an editable install
    sys.path.insert(0, str(ROOT / "src"))

import streamlit as st  # noqa: E402

from invoice_recon import config, pipeline, storage, view  # noqa: E402
from invoice_recon.models import STATUSES  # noqa: E402
from invoice_recon.money import format_cents  # noqa: E402
from invoice_recon.reference import load_reference  # noqa: E402

st.set_page_config(page_title="Invoice review", layout="wide")

PAGES = ("Queue", "Invoice detail", "Summary")


def _open_detail(file_id: str) -> None:
    st.session_state["selected"] = file_id
    st.session_state["page"] = "Invoice detail"


def _flash(kind: str, message: str) -> None:
    st.session_state["flash"] = (kind, message)


def _show_flash() -> None:
    flash = st.session_state.pop("flash", None)
    if flash:
        getattr(st, flash[0])(flash[1])


def render_queue(states, summary) -> None:
    st.header("Review queue")
    if summary is not None:
        cols = st.columns(len(STATUSES) + 1)
        for col, status in zip(cols, STATUSES):
            col.metric(status, summary.counts.get(status, 0))
        cols[-1].metric("Recoverable", format_cents(summary.recoverable_cents))
    left, right = st.columns(2)
    statuses = left.multiselect("Filter by status", STATUSES)
    review = right.multiselect("Filter by review status", pipeline.REVIEW_STATUSES)
    rows = view.filter_rows(view.queue_rows(states), statuses, review)
    st.caption(f"{len(rows)} of {len(states)} documents")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    if rows:
        file_id = st.selectbox("Open document", [str(r["file_id"]) for r in rows], key="queue_open")
        st.button(f"Open {file_id}", on_click=_open_detail, args=(file_id,))


def render_correction_form(state) -> None:
    raw = state.extraction.raw
    st.subheader("Correct an extracted field")
    if state.extraction.status != "ok" or raw is None:
        st.info("There is no extraction to correct for this document.")
        return
    with st.form(f"correction-{state.file_id}", clear_on_submit=True):
        field = st.selectbox("Field", view.correctable_fields(raw))
        value = st.text_input("New value (as printed on the invoice)")
        make_null = st.checkbox("Set the field to empty (null) instead")
        reason = st.text_input("Reason")
        submitted = st.form_submit_button("Save correction and rerun reconciliation")
    if submitted:
        if not make_null and not value.strip():
            st.error("Enter a new value, or tick the empty (null) box.")
            return
        try:
            pipeline.add_correction(state.file_id, field, None if make_null else value.strip(), reason.strip())
        except (ValueError, storage.StorageError) as exc:
            st.error(f"Correction not saved: {exc}")
            return
        _flash("success", f"Correction to {field} saved; the whole batch was reconciled again.")
        st.rerun()


def render_review_form(state) -> None:
    st.subheader("Review status and comment")
    with st.form(f"review-{state.file_id}"):
        options = list(pipeline.REVIEW_STATUSES)
        status = st.selectbox("Review status", options, index=options.index(state.review.status))
        comment = st.text_area("Comment", value=state.review.comment)
        submitted = st.form_submit_button("Save review")
    if submitted:
        try:
            pipeline.update_review(state.file_id, status, comment)
        except (ValueError, storage.StorageError) as exc:
            st.error(f"Review not saved: {exc}")
            return
        _flash("success", "Review saved.")
        st.rerun()
    if state.review.updated_at:
        st.caption(f"Last updated {state.review.updated_at}")


def render_detail(states) -> None:
    st.header("Invoice detail")
    if not states:
        st.info("No documents yet. Run `python -m invoice_recon.cli run` first.")
        return
    ids = sorted(states, key=lambda f: states[f].ingest_seq)
    if st.session_state.get("selected") not in ids:
        st.session_state["selected"] = ids[0]
    file_id = st.selectbox("Document", ids, key="selected")
    state = states[file_id]
    rec = state.reconciliation
    ext = state.extraction

    img_col, data_col = st.columns([1, 1])
    with img_col:
        image = ROOT / state.image_path
        if image.is_file():
            st.image(str(image))
        else:
            st.warning(f"Image not found: {state.image_path}")
    with data_col:
        st.markdown(f"**Status:** `{rec.status if rec else 'not reconciled'}`")
        if rec is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Expected", view.money_or_dash(rec.expected_cents))
            c2.metric("Billed", view.money_or_dash(rec.billed_cents))
            c3.metric("Difference", view.money_or_dash(rec.difference_cents))
            if rec.duplicate_of:
                st.warning(f"Duplicate of `{rec.duplicate_of}` (processed earlier). Not counted as payable.")
            if rec.error:
                st.error(rec.error)
            for key, reason in rec.errors.items():
                st.error(f"{key}: {reason}")
        badge = view.provenance_label(ext.source)
        (st.warning if ext.source == "simulated" else st.info)(
            f"Extraction source: {badge}. Model: {ext.model or '-'}, prompt: {ext.prompt_version or '-'}"
        )
        if ext.error:
            st.error(f"Extraction error: {ext.error}")
        if ext.raw is not None:
            st.markdown("**Extracted values: original vs effective (with corrections)**")
            st.dataframe(view.raw_comparison_rows(ext.raw, state), use_container_width=True, hide_index=True)
            if ext.raw.warnings:
                st.caption("Extraction warnings: " + "; ".join(ext.raw.warnings))
        if ext.underlying is not None:
            with st.expander("Real model response for the same image (kept alongside the simulation)"):
                under = ext.underlying
                st.markdown(f"Source: {view.provenance_label(under.source)}")
                if under.error:
                    st.error(under.error)
                if under.raw is not None:
                    st.json(under.raw.model_dump())

    orders, receipts = load_reference(pipeline.default_reference_paths())
    po = view.matched_po(state, orders)
    st.subheader("Matched purchase order and receipts")
    if po is None:
        st.write("No purchase order matched.")
    else:
        st.caption(f"PO {po.po_id}, supplier {po.supplier_id}, source {po.source}")
        a, b = st.columns(2)
        a.dataframe(view.po_rows(po), use_container_width=True, hide_index=True)
        rrows = view.receipt_rows(po.po_id, receipts)
        if rrows:
            b.dataframe(rrows, use_container_width=True, hide_index=True)
        else:
            b.write("No receipts for this PO.")

    st.subheader("Lines: ordered, received, billed")
    lines = view.line_table_rows(state)
    if lines:
        st.dataframe(lines, use_container_width=True, hide_index=True)
    else:
        st.write("No line comparison available for this status.")

    st.subheader("Findings")
    findings = view.finding_rows(state)
    if findings:
        st.dataframe(findings, use_container_width=True, hide_index=True)
    else:
        st.write("No findings.")

    st.subheader("Draft note")
    render_note(state)

    render_correction_form(state)
    history = view.correction_history_rows(state)
    if history:
        st.markdown("**Correction history** (the original extraction is never changed)")
        st.dataframe(history, use_container_width=True, hide_index=True)
    render_review_form(state)


def render_note(state) -> None:
    note = state.note
    if not note:
        st.write("No draft note: notes are only drafted for discrepant, unresolved and duplicate invoices.")
        return
    st.write(note["text"])
    st.caption(f"Provenance: {view.provenance_label(note['source'])} ({note['basis']}); prompt {note['prompt_version']}")
    if note["guard_passed"]:
        st.caption("Number guard: passed")
    else:
        st.warning("Needs review: number guard failed. " + "; ".join(note["guard_errors"]))
    if note.get("error"):
        st.caption(f"Note: {note['error']}")


def render_summary(states, summary) -> None:
    st.header("Summary")
    if summary is None:
        st.info("No summary yet. Run `python -m invoice_recon.cli run` first.")
        return
    st.dataframe(
        [{"status": s, "invoices": summary.counts.get(s, 0)} for s in STATUSES], use_container_width=True, hide_index=True
    )
    c1, c2 = st.columns(2)
    c1.metric("Recoverable (discrepant invoices only)", format_cents(summary.recoverable_cents))
    c2.metric("Net difference (discrepant invoices only)", format_cents(summary.net_difference_cents))
    st.subheader("Findings by type")
    counts = view.summary_finding_counts(states)
    if counts:
        st.dataframe(
            [{"finding": k, "meaning": view.FINDING_LABELS.get(k, k), "count": v} for k, v in counts.items()],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("No findings.")
    st.subheader("Insight")
    insight = storage.load_insight()
    if insight is None:
        st.write("No insight yet. Run `python -m invoice_recon.cli run` first.")
    else:
        st.write(insight["text"])
        st.caption(f"Provenance: {view.provenance_label(insight['source'])} ({insight['basis']})")
        if not insight["guard_passed"]:
            st.warning("Needs review: number guard failed. " + "; ".join(insight["guard_errors"]))


def main() -> None:
    st.title("Invoice reconciliation review")
    st.sidebar.radio("Page", PAGES, key="page")
    st.sidebar.caption(f"MODEL_MODE: {config.MODEL_MODE} (the UI never calls a model)")
    _show_flash()
    try:
        states, load_errors = storage.load_all_tolerant()
        summary = storage.load_summary()
    except storage.StorageError as exc:
        st.error(str(exc))
        return
    for file_id, message in load_errors.items():
        st.error(f"Document {file_id} could not be loaded and is hidden: {message}")
    page = st.session_state["page"]
    if page == "Queue":
        render_queue(states, summary)
    elif page == "Invoice detail":
        render_detail(states)
    else:
        render_summary(states, summary)


main()
