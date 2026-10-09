# Workflow log

Running log for the "one workflow example" and the LLM usage note. Append an entry after a significant
instruction, generated component, check, or correction. Keep entries short; full chat logs are not needed.

## Entry template

### YYYY-MM-DD HH:MM — <short title>
- **Instruction:** (short excerpt of what was asked)
- **Configuration involved:** (CLAUDE.md section, docs file, prompt version, skill)
- **Produced:** (files / components)
- **How it was checked:** (test, manual inspection, comparison with expected results)
- **Correction or improvement:** (what was wrong and how it was fixed, or "none")

---

### 2026-10-08 16:29 - Phase 0 setup
- **Instruction:** Create the architecture layout, complete Phase 0, and create a root virtual environment.
- **Configuration involved:** CLAUDE.md, ARCHITECTURE.md, PLAN.md; root documents preserved and copied into docs/ for existing links.
- **Produced:** Repository scaffold, Python 3.12 .venv, six pinned dependencies, editable src package, replay-default configuration, environment template, Git exclusions, and one configuration test. Later-phase files are explicitly placeholders; generated JSON datasets and expected results are null until Phase 6.
- **How it was checked:** pip install --no-compile -r requirements.txt succeeded; pytest: 1 passed; pip check: no broken requirements; editable package import succeeded; all 10 starter copies byte-identical; .env, .venv and runtime state ignored by Git.
- **Correction or improvement:** Starter files were in the root instead of data/inputs; copied unchanged, preserving originals. Added .gitattributes to preserve input bytes on checkout. Network installation required sandbox escalation. No model calls made.
- **Time:** Approximately 22 minutes; exceeded the 15-minute estimate because Windows package installation and bytecode compilation took most of the time. Scope unchanged; Phase 1 not started.

### 2026-10-08 17:00 - Phase 0 verification round (no git workflow)
- **Instruction:** Implement Phase 0; `.baseline/` replaces git.
- **Configuration involved:** CLAUDE.md, PLAN.md Phase 0, implementer role.
- **Produced:** Added `.baseline/` to `.gitignore`; added one-line reasons to `requirements.txt`; emptied a non-empty credential value from `.env.example` (names only now).
- **How it was checked:** `pip install -r requirements.txt` in existing .venv; `MODEL_MODE=replay pytest -q`.
- **Correction or improvement:** Layout, config.py and the log header already existed from an earlier pass; only gaps were fixed.

### 2026-10-08 17:20 - Phase 1 core domain
- **Instruction:** Run Phase 1 through implement → test → review.
- **Configuration involved:** CLAUDE.md loop, PLAN.md Phase 1, implementer and reviewer agents, DECISIONS.md.
- **Produced:** models, money, reference, normalize, matching, reconcile (pure functions) and 52 tests incl. the seed test (4/4 expected results reproduced, no model call).
- **Decisions made:** The implementer raised Q1–Q3; the user answered and they were recorded as A11 (ambiguous receipt/PO → unresolved, never sum), A12 (missing line description → invalid, code changed in a follow-up), A13 (null supplier_id → unresolved, never duplicate).
- **Review:** round 1 PASS, 2 minors deferred (corrections targeting missing line/field must not crash a batch; normalized=None gives invalid with no error text).
- **Time:** ~25 min including the question round.

### 2026-10-08 20:20 - Phase 2 extraction
- **Instruction:** Run Phase 2 through implement → test → review; one live Gemini run approved by the user.
- **Configuration involved:** CLAUDE.md loop, PLAN.md Phase 2, implementer and reviewer agents, `prompts/extract-v1.md`.
- **Produced:** extraction package (Gemini provider, cache, simulations, service), `scripts/extract_images.py`, 17 tests (69 total).
- **Live run:** `gemini-2.5-flash`, 3 live calls (clean, missing-reference, wrong-price); `duplicate.png` has the same image hash as `clean.png`, so it was served from cache. Responses saved to `data/model_cache/extract/`.
- **Inspection against the images:** all four correct. INV-1/PO-1/CAB-1 5×20.00=100.00 (clean, duplicate); INV-2/PO-2 5×24.00=120.00 (wrong-price); INV-3 po_id null with warning "po_id is missing", 100.00 (missing-reference). Line description is null in all (images have none).
- **Checkpoint:** with GEMINI_API_KEY unset and MODEL_MODE=replay all four extract from cache; 69 tests pass.
- **Review:** round 1 PASS; 1 minor deferred (cache entry missing `model`/`raw_text` should fail).

### 2026-10-08 20:30 - Phase 3 decision: A12 revised
- **What changed:** `docs/DECISIONS.md` A12 now says a null/missing line description is allowed and does not affect validity (was: invalid). Q1 removed from Open questions. Snapshot of the earlier file: `ai-workflow/snapshots/DECISIONS.md.phase3.md`.
- **Why:** the implementer found the end-to-end replay run made all four seed invoices `invalid`, because the seed images print no item description and the cached extractions have null descriptions. User chose option (a) and asked for the rule to be removed everywhere.
- **Follow-up:** `normalize.py` check and its tests removed in Phase 3 round 2.
- **Also changed (20:40):** `docs/ARCHITECTURE.md` validity rule now excludes `description` (A12). Snapshot: `ai-workflow/snapshots/ARCHITECTURE.md.phase3.md`.

### 2026-10-08 20:45 - Phase 3 storage, pipeline, CLI
- **Instruction:** Run Phase 3 through implement → test → review.
- **Produced:** documents discovery, storage (atomic writes), pipeline (run/reconcile/corrections/review), CLI (run, reconcile, reset --yes); 84 tests.
- **Decision made:** implementer found A12 (null description = invalid) made all four seed invoices invalid, because the seed images print no description. User chose to allow null description; A12 revised, ARCHITECTURE.md updated, normalize.py check removed (round 2 of implementation).
- **Review:** round 1 PASS; 2 minors deferred (one corrupt state file aborts the batch; typo).

### 2026-10-08 - Phase 4 round 2: ARCHITECTURE.md Summary line
- **What changed:** `docs/ARCHITECTURE.md` UI section, Summary bullet: "recoverable total by finding type" became "recoverable total and finding counts by type (per-type amounts are not attributed, because no rule defines how)". Snapshot: `ai-workflow/snapshots/ARCHITECTURE.md.phase4.md`.
- **Why:** review finding #4; the doc promised an amount per type that the app deliberately does not compute.

## Phase 4 — manual walkthrough (2026-10-08)
User ran the UI after `cli run`: queue shows 4 documents with status/review filters; opened wrong-price, corrected `lines[0].unit_price` 24.00 -> 20.00, restarted Streamlit. Correction persisted (queue `corrected: yes`, history entry, original value still shown). Status stayed `discrepant` because `invoice_total` (120.00) was not changed; expected $100.00 vs billed $120.00 — correct behaviour. Decision: corrections stay free-form (original preserved, history visible). Phase 4 approved by user. Review: round 1 CHANGES_REQUESTED (streamlit-version-dependent row selection, importorskip), round 2 PASS.

### 2026-10-09 - Phase 7 round 2: Q-P7-1 resolved
- **Decision (user):** `count_as_payable` is false ONLY for duplicates; no rule makes unresolved invoices non-payable. The `qty_over_received` oracle finding stays (domain.md rule 3 compares billed qty with ordered and received qty).
- **What changed:** `scripts/compute_expected.py` (flag false only for duplicates), `data/expected/` regenerated, `scripts/check_report.py` (workaround removed, field compared for all cases, M3 payable count restricted to reconciled/discrepant, `po_source` shown repo-relative), `reports/check-results.md` regenerated. `docs/DECISIONS.md`: Q-P7-1 removed from Open questions, rows A14 and A15 added. Snapshot: `ai-workflow/snapshots/DECISIONS.phase7.md`.
- **Why:** the expected file disagreed with ARCHITECTURE and the application; the checker had been skipping the field.

### 2026-10-09 - Phase 8 documentation and AI configuration
- **Instruction:** Complete README.md, ai-workflow/README.md and manifest.json; record config changes.
- **Config files changed:** `README.md` (skeleton replaced by full documentation); `ai-workflow/README.md` and `ai-workflow/manifest.json` (template content replaced, `"template": true` removed); `ai-workflow/.env.example` (template variable `MODEL_API_KEY` replaced by the project variable names, no values). No snapshots were needed: none of these had been used by the loop before.
- **Facts checked, not assumed:** no hooks, MCP or settings file exist under `.claude/`; Claude Code version not discoverable (`claude` not on PATH), so recorded as not-exportable; model ID `gemini-2.5-flash` read from `data/model_cache/` entries; parameters from `src/invoice_recon/config.py`.
- **How it was checked:** in replay with no API key, after `cli reset --yes`, `MODEL_MODE=replay pytest -q` gave 122 passed and `cli run` processed 8 documents with 0 extraction failures (7 cached, 1 simulated); Streamlit started on a test port. The earlier `data/state/` was backed up and restored afterwards.
- **Found while documenting (not fixed, reported):** in replay only 2 of 7 notes are cached real responses, five use the labelled deterministic template; `.claude/skills/verify-reconciliation` refers to files that do not exist; DECISIONS D6 ("no subagents") is outdated.