PHASE: 8  ROUND: 1  BASE: .baseline/ (saved after Phase 7)
VERDICT: CHANGES_REQUESTED
MECHANICAL CHECKS:
- K1 pass — `tools/baseline.py status data/inputs/` printed nothing.
- K2 pass — 122 passed, 2 warnings. I ran it with MODEL_MODE=replay but did not unset GEMINI_API_KEY.
- K3 to K6 n/a — no src/ or app/ changes in Phase 8, so I did not run them.
- K7 pass — .gitignore lists `.env` (line 1) and `.baseline/` (line 8). The AIza key search found no hits; one `.pytest_cache` permission error appeared.
- K8 n/a — no tests changed.
- K9 pass — `tools/baseline.py status prompts/` printed nothing.
- K10 n/a — no UI changes.
CHECKPOINT: met on the evidence I could check. The pytest run is green in replay. The README lists the commands for `pytest`, `cli run` and `streamlit` with no key. The cache holds extract 7, note 7 and insight 1, which matches the README. I did not run `cli run` or the UI myself, because that would write to `data/state/`.
PREVIOUS FINDINGS: none (round 1)
FINDINGS:
- #1 [minor] README.md:283-286 and ai-workflow/manifest.json:500 — Phase 8 time and review status are written as "finish time not yet recorded" and "phase 8 review pending at the time of writing". Update both after the loop closes, or the submitted docs will carry stale statements.
- #2 [minor] README.md:61-67 — The text says "verified on 2026-10-09 ... after `cli reset --yes`" and "re-verified", but the same section later says the state backup was restored. No finding on correctness. Only keep this wording if the orchestrator really did both runs; I could not reproduce it without touching `data/state/`.
NOTES: Claims I verified against the repo:
- google-genai==2.29.0, streamlit 1.65.0, Python 3.12.10, max tokens 2048, timeout 60 s, 2 retries and temperature 0 all match config.py and requirements.txt.
- check-results.md says "11 of 11". The decision IDs D1-D10, E1-E7, C1-C10 and A1-A15 all exist in DECISIONS.md.
- The snapshot filenames listed in the docs exist. `ai-workflow/.env.example` has the same names as the root `.env.example`. The template files were renamed and no `template` flag is left in the manifest. Hooks and MCP are marked not-used, and the subagents are marked used.
- I could not verify the Claude Code version 2.1.295 and the Sonnet 5.5 model, which the author supplied (D10). The docs correctly label them "stated by the author".
