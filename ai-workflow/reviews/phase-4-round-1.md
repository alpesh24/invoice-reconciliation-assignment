PHASE: 4  ROUND: 1  BASE: .baseline/ (last approved phase)
VERDICT: CHANGES_REQUESTED
MECHANICAL CHECKS:
- K1 pass — baseline.py status data/inputs/ is empty.
- K2 fail — `env -u GEMINI_API_KEY MODEL_MODE=replay pytest -q` gave 95 passed, 1 failed: tests/test_view.py::test_ui_pages_render_without_exceptions. TypeError "ArrowMixin.dataframe() got an unexpected keyword argument 'on_select'".
- K3 pass. K4 n/a. K5 n/a. K6 pass (only extraction/gemini.py). K7 pass. K8 pass (two pytest.importorskip("streamlit")). K9 pass. K10 pass.
CHECKPOINT: not met. Test gate red; manual walkthrough not run; no Phase 4 walkthrough note in ai-workflow/workflow-log.md.
FINDINGS:
- #1 [blocker] tests/test_view.py:134-143 and app/streamlit_app.py:52 — `pytest` resolves to Python 3.11 (older streamlit without st.dataframe on_select/selection_mode); `python` resolves to 3.12 with streamlit 1.65.0 (the pin). Queue page raises on the older version. Fix: align environment with requirements.txt (run pytest via venv / 3.12), and make the queue not hard-depend on row selection (e.g. st.selectbox or st.button to open a document). Re-run until green.
- #2 [major] tests/test_view.py:134,147 — pytest.importorskip("streamlit") silently skips the UI correction flow if streamlit is missing. Streamlit is a pinned requirement; import directly.
- #3 [minor] app/streamlit_app.py — use_container_width=True deprecated in streamlit 1.65; use width="stretch" or leave.
- #4 [minor] docs/ARCHITECTURE.md:269 vs app/streamlit_app.py:54-60 — doc says summary shows "recoverable total by finding type"; UI shows total recoverable plus finding counts by type. Record deviation in DECISIONS.md or align doc.
NOTES: Design looks right: corrections via pipeline.add_correction re-reconcile whole batch and persist; original untouched; provenance badges present; no model calls; load_all_tolerant tested.
