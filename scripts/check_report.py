"""Expected vs observed: runs the pipeline in replay mode and writes reports/check-results.md.

Expected values come from data/expected/expected-results.json (scripts/compute_expected.py, independent of src/).
Observed values come from the application pipeline, run in a temporary state directory so data/state/ is
untouched. Never calls a model: MODEL_MODE is forced to replay before the package is imported.

Usage: python scripts/check_report.py
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

os.environ["MODEL_MODE"] = "replay"  # must happen before importing invoice_recon.config
os.environ["USE_SIMULATIONS"] = "1"
os.environ["SIMULATED_FAILURES"] = ""

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invoice_recon import pipeline, storage  # noqa: E402
from invoice_recon.extraction.base import ExtractionResult  # noqa: E402

EXPECTED_PATH = ROOT / "data" / "expected" / "expected-results.json"
REPORT_PATH = ROOT / "reports" / "check-results.md"

# The expected file uses its own finding vocabulary; only this code differs from the application's.
CODE_MAP = {"price_diff": "price_differs"}
MILESTONES = {"M1": "A clean invoice matches its PO and receipt; amounts agree with the independent calculation",
              "M2": "Wrong unit price gives the expected discrepancy, linked to the invoice and the agreed price",
              "M3": "Duplicate is flagged and excluded from payable totals",
              "M4": "Missing PO reference stays unresolved; no invented match or amount",
              "M5": "Correction reruns reconciliation, updates the saved result, survives a restart"}


def observe(state) -> dict:
    """Comparable view of one saved invoice state (read from the application's output)."""
    rec = state.reconciliation
    norm = state.normalized
    sku_by_line = {ln.line_no: ln.sku for ln in (norm.lines if norm else [])}
    line_findings: dict[str, set[str]] = {}
    top_codes = []
    for f in rec.findings:
        code = CODE_MAP.get(f.code, f.code)
        if f.line_no is None:
            top_codes.append(code)
        else:
            line_findings.setdefault(sku_by_line.get(f.line_no, f"line{f.line_no}"), set()).add(code)
    diff = rec.difference_cents
    return {
        "invoice_number": norm.invoice_number if norm else None,
        "supplier_id": norm.supplier_id if norm else None,
        "po_id": norm.po_id if norm else None,
        "status": rec.status,
        "expected_cents": rec.expected_cents,
        "billed_cents": rec.billed_cents,
        "difference_cents": diff,
        "count_as_payable": rec.count_as_payable,
        "recoverable_cents": diff if rec.status == "discrepant" and diff is not None and diff > 0 else 0,
        "line_findings": line_findings,
        "reason": top_codes[0] if top_codes else None,
        "duplicate_of": rec.duplicate_of,
    }


def compare(exp: dict, obs: dict) -> list[tuple[str, object, object, bool]]:
    """(field, expected, observed, ok) for every field the expected record defines."""
    rows = []
    for key, want in exp.items():
        if key in ("file_id", "rule"):
            continue
        if key == "line_findings":
            want = {sku: set(codes) for sku, codes in want.items()}
        got = obs.get(key)
        rows.append((key, want, got, want == got))
    return rows


def rel_path(p: str | None) -> str | None:
    """Repo-relative POSIX path for report output (no machine-specific absolute paths)."""
    if not p:
        return p
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p


def fmt(value) -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {sorted(v)}" for k, v in sorted(value.items())) + "}" if value else "{}"
    return str(value)


def state_dict(states) -> dict:
    return {fid: observe(s) for fid, s in states.items()}


def case_row(check_id: str, file_id: str, exp: dict, obs: dict | None, extra_notes: list[str], failed_extraction):
    if obs is None:
        return [check_id, file_id, "(expected record)", failed_extraction or "no observed result", "FAIL", ""]
    comps = compare(exp, obs)
    ok = all(c[3] for c in comps)
    exp_txt = "<br>".join(f"{k}={fmt(w)}" for k, w, _g, _o in comps)
    obs_txt = "<br>".join(f"{k}={fmt(g)}" for k, _w, g, _o in comps)
    bad = [k for k, _w, _g, o in comps if not o]
    notes = list(extra_notes)
    if bad:
        notes.append("mismatch: " + ", ".join(bad))
    return [check_id, file_id, exp_txt, obs_txt, "PASS" if ok else "FAIL", "; ".join(notes)]


def provenance(states, file_id) -> str:
    ext = states[file_id].extraction
    return f"extraction source={ext.source}" if ext.status == "ok" else f"extraction FAILED: {ext.error}"


def main() -> int:
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    cases = {c["file_id"]: c for c in expected["cases"]}
    ref_cases = expected["reference_cases"]
    results: list[list[str]] = []  # report rows
    extras: list[list[str]] = []  # extra check rows (id, check, expected, observed, result, notes)

    with tempfile.TemporaryDirectory() as tmp:
        state_dir = Path(tmp)
        states, summary = pipeline.run_pipeline(state_dir=state_dir)
        before = state_dict(states)
        before_summary = {"status_counts": {k: v for k, v in summary.counts.items() if v},
                          "recoverable_cents": summary.recoverable_cents}

        def row_for(check_id, file_id, note=""):
            exp = cases[file_id]["before_correction"]
            notes = [provenance(states, file_id)] + ([note] if note else [])
            if states[file_id].extraction.status != "ok":
                notes.append("replay has no cached response for this image, not faked; run `MODEL_MODE=live cli run` once "
                             "(needs user approval) to cache it")
            obs = before.get(file_id) if states[file_id].reconciliation else None
            return case_row(check_id, file_id, exp, obs, notes, provenance(states, file_id))

        # M1-M4 and the extra before-correction cases.
        m_rows = {}
        m_rows["M1"] = row_for("M1", ref_cases["M1"], "also checked against domain.md seed expectation (10000/10000/0)")
        wp = states["wrong-price"].reconciliation
        link = next((ln for ln in wp.lines if ln.difference_cents), None)
        m2_note = (f"links: file_id=wrong-price, PO {wp.po_id} ({rel_path(wp.po_source)}), agreed unit "
                   f"{link.agreed_unit_cents if link else None} vs billed {link.billed_unit_cents if link else None} cents")
        m_rows["M2"] = row_for("M2", ref_cases["M2"], m2_note)
        dup = states["duplicate"].reconciliation
        m3 = row_for("M3", ref_cases["M3"], f"duplicate_of={dup.duplicate_of}")
        # Totals check: the duplicate's amount must not appear in payable totals.
        payable = sum(1 for s in states.values() if s.reconciliation.count_as_payable
                      and s.reconciliation.status in ("reconciled", "discrepant"))
        want_payable = sum(1 for c in cases.values() if c["before_correction"]["count_as_payable"]
                           and c["before_correction"]["status"] in ("reconciled", "discrepant"))
        totals_ok = payable == want_payable and summary.recoverable_cents == expected["summary_before_correction"]["recoverable_cents"]
        m3[3] += f"<br>payable_invoices={payable}, recoverable_cents={summary.recoverable_cents}"
        m3[2] += f"<br>payable_invoices={want_payable}, recoverable_cents={expected['summary_before_correction']['recoverable_cents']}"
        if not totals_ok:
            m3[4] = "FAIL"
            m3[5] += "; mismatch: payable totals"
        m_rows["M3"] = m3
        m_rows["M4"] = row_for("M4", ref_cases["M4"], "no PO matched; expected and difference must be null")

        # M5: apply the documented correction, reload from disk, verify, then simulate a restart.
        m5_file = ref_cases["M5"]
        c = cases[m5_file]
        corr = c["correction"]
        m5_steps: list[tuple[str, str, str, bool]] = []  # (step, expected, observed, ok)
        pre = before[m5_file]
        exp_pre = c["before_correction"]
        m5_steps.append(("before: status", exp_pre["status"], pre["status"], pre["status"] == exp_pre["status"]))
        m5_steps.append(("before: po_id", exp_pre["po_id"], str(pre["po_id"]), pre["po_id"] == exp_pre["po_id"]))
        m5_steps.append(("before: expected/difference null", "None/None",
                         f"{pre['expected_cents']}/{pre['difference_cents']}",
                         pre["expected_cents"] is None and pre["difference_cents"] is None))
        try:
            pipeline.add_correction(m5_file, corr["field"], corr["to"], "Check report: image prints PO-5, "
                                    "simulated extraction misread it as PO-S", state_dir=state_dir)
            reloaded = storage.load_all(state_dir)  # fresh read from disk
            reloaded_summary = storage.load_summary(state_dir)
            after = state_dict(reloaded)
            comps = compare(c["after_correction"], after[m5_file])
            for k, w, g, ok in comps:
                m5_steps.append((f"after correction (reloaded from disk): {k}", fmt(w), fmt(g), ok))
            st = reloaded[m5_file]
            m5_steps.append(("original extraction immutable", f"po_id={corr['from']}", f"po_id={st.extraction.raw.po_id}",
                             st.extraction.raw.po_id == corr["from"]))
            hist = [(h.field, h.original, h.corrected) for h in st.corrections]
            want_hist = [(corr["field"], corr["from"], corr["to"])]
            m5_steps.append(("correction history saved", str(want_hist), str(hist), hist == want_hist))
            got_after = {"status_counts": {k: v for k, v in reloaded_summary.counts.items() if v},
                         "recoverable_cents": reloaded_summary.recoverable_cents}
            m5_steps.append(("saved batch summary after correction", str(expected["summary_after_correction"]),
                             str(got_after), got_after == expected["summary_after_correction"]))
            others_ok = all(after[f] == before[f] for f in before if f != m5_file)
            m5_steps.append(("other invoices unchanged", "unchanged", "unchanged" if others_ok else "changed", others_ok))
            # Restart: a fresh `run` and a fresh `reconcile` over the same state dir must keep the correction.
            pipeline.run_pipeline(state_dir=state_dir)
            pipeline.reconcile_all(state_dir=state_dir)
            restarted = storage.load_all(state_dir)
            r = observe(restarted[m5_file])
            m5_steps.append(("after restart (run + reconcile + reload): status", "reconciled", r["status"],
                             r["status"] == "reconciled"))
            m5_steps.append(("after restart: po_id / correction kept", "PO-5 / 1 correction",
                             f"{r['po_id']} / {len(restarted[m5_file].corrections)} correction(s)",
                             r["po_id"] == corr["to"] and len(restarted[m5_file].corrections) == 1))
        except Exception as exc:  # report, never crash the report
            m5_steps.append(("correction run", "no error", f"{type(exc).__name__}: {exc}", False))
        m5_ok = all(s[3] for s in m5_steps)
        m5_notes = [provenance(states, m5_file),
                    "before-correction input is the simulated misread (data/simulations.json), labelled source=simulated"]
        m_rows["M5"] = ["M5", m5_file,
                        "<br>".join(f"{s[0]}: {s[1]}" for s in m5_steps),
                        "<br>".join(f"{s[0]}: {s[2]}" for s in m5_steps),
                        "PASS" if m5_ok else "FAIL", "; ".join(m5_notes)]

        for key in ("M1", "M2", "M3", "M4", "M5"):
            results.append(m_rows[key])

        # Extra reference-data cases (same comparison, before correction).
        for file_id in cases:
            if file_id in ref_cases.values():
                continue
            extra_note = {
                "conflicting-supplier": "PO-1 exists but belongs to S1; amounts equal PO-1, so amount matching would wrongly accept it",
                "multi-line-price": "difference attributed to the ADP-2 line only",
                "short-receipt": "billed = ordered, received 4 of 6; no amount invented for the shortfall (DECISIONS A1)",
            }.get(file_id, "")
            extras.append(row_for("extra", file_id, extra_note))

        # Per-line attribution for the multi-line invoice.
        ml = states["multi-line-price"].reconciliation
        by_sku = {ln.sku: ln.difference_cents for ln in ml.lines}
        ok = by_sku == {"CAB-1": 0, "ADP-2": 1000}
        extras.append(["extra", "multi-line-price (per line)", "line differences CAB-1=0, ADP-2=1000 (hand calc)",
                       f"line differences {by_sku}", "PASS" if ok else "FAIL", "checks attribution to the right PO line"])

        # Batch summary before correction.
        ok = before_summary == expected["summary_before_correction"]
        extras.append(["extra", "batch summary (before correction)", str(expected["summary_before_correction"]),
                       str(before_summary), "PASS" if ok else "FAIL", "recoverable excludes duplicate and unresolved"])

    # Batch resilience: one failing extraction must not stop the batch (CLAUDE.md rule 9).
    def flaky(file_id, path):
        if file_id == "clean":
            return ExtractionResult(status="failed", error="simulated API failure (check report)")
        return pipeline.default_extractor()(file_id, path)

    with tempfile.TemporaryDirectory() as tmp:
        st2, sm2 = pipeline.run_pipeline(state_dir=Path(tmp), extractor=flaky)
        others = [s for f, s in st2.items() if f != "clean"]
        ok = (st2["clean"].reconciliation.status == "extraction_failed" and len(others) == len(st2) - 1
              and all(s.reconciliation is not None and s.reconciliation.status != "extraction_failed" for s in others))
        extras.append(["extra", "batch continues after one extraction failure",
                       "clean=extraction_failed, all other invoices still processed",
                       f"clean={st2['clean'].reconciliation.status}; others={sorted({s.reconciliation.status for s in others})}",
                       "PASS" if ok else "FAIL",
                       "forced failure by the check script (labelled simulated here only); the duplicate then becomes the original, "
                       "which is why order of processing is explicit (DECISIONS C5)"])

    write_report(results, extras)
    all_rows = results + extras
    failed = [r for r in all_rows if r[4] != "PASS"]
    print(f"{len(all_rows) - len(failed)}/{len(all_rows)} checks passed; report: {REPORT_PATH}")
    return 1 if failed else 0


def write_report(results, extras) -> None:
    def table(rows):
        out = ["| ID | Case | Expected | Observed | Result | Notes |", "|---|---|---|---|---|---|"]
        for r in rows:
            out.append("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ") for x in r) + " |")
        return out

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Check results",
        "",
        f"Generated by `python scripts/check_report.py` on {stamp}. Do not edit by hand.",
        "",
        "- Mode: `MODEL_MODE=replay` (forced by the script); no model call is made and no API key is needed.",
        "- Expected: `data/expected/expected-results.json`, computed by `scripts/compute_expected.py` from structured "
        "records, independent of the application.",
        "- Observed: the application pipeline (`run_pipeline`, `add_correction`, `reconcile_all`), run in a temporary "
        "state directory; `data/state/` is not touched.",
        "- `count_as_payable` is compared for every case; it is false only for duplicates (DECISIONS Q-P7-1). "
        "Unresolved invoices are also verified to stay out of the totals (expected/difference null, recoverable 0, "
        "batch recoverable).",
        "- Amounts are integer USD cents. The expected file calls the unit-price finding `price_differs`; the "
        "application calls it `price_diff` (mapped in the script).",
        "",
        "## Mandatory checks M1-M5",
        "",
        *[f"- **{k}**: {v}" for k, v in MILESTONES.items()],
        "",
        *table(results),
        "",
        "## Additional cases",
        "",
        *table(extras),
        "",
        "## Summary",
        "",
        f"- Passed: {sum(1 for r in results + extras if r[4] == 'PASS')} of {len(results) + len(extras)}.",
    ]
    failed = [r for r in results + extras if r[4] != "PASS"]
    if failed:
        lines.append("- Failures (explained in the Notes column): " + ", ".join(f"{r[0]} {r[1]}" for r in failed))
    else:
        lines.append("- No failures.")
    lines += ["", "## Limitations of these checks", "",
              "- Observed extractions come from the replay cache; images added without a cached response would show "
              "`extraction FAILED` rows here, which is reported as is and never filled in.",
              "- `correction` is checked from a **simulated** misread (labelled `source=simulated`); its real cached "
              "response is not used for the before-correction state.",
              "- A restart is simulated by a fresh `run_pipeline`, `reconcile_all` and a fresh read from disk in the same "
              "process, not by launching Streamlit.",
              ""]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
