# AI workflow used during this exercise

Machine-readable record: [manifest.json](manifest.json). Statuses use `not-used`, `default`, `used`, `redacted`
and `not-exportable`. No credentials are included anywhere in this folder.

## Tools and models

**Development time**

| Item | Record |
|---|---|
| Coding tool | Claude Code: one main session (the "orchestrator", which does not write application code) and two project subagents, `implementer` and `reviewer`. |
| Claude Code version | 2.1.295 (stated by the author) |
| Orchestrator model | Sonnet 5.5 (`claude-sonnet-5-5`, stated by the author). The subagents are defined with `model: inherit`, so they use the orchestrator's model. |
| Settings changed | None found: there is no project `settings.json`, no hooks and no MCP configuration (`.claude/` holds only `agents/` and `skills/`). Default permissions applied. |
| Plugins / extensions | not-used |

**Inside the application** (not a development tool): Gemini through `google-genai==2.29.0`, model
`gemini-2.5-flash` (set via `GEMINI_MODEL`, recorded in every cache entry), temperature 0, max output 2048
tokens, 60 s timeout, 2 retries with backoff. Extraction uses JSON output with the `RawExtraction` response
schema; notes and the insight use plain text. Prompt files: `prompts/extract-v1.md`, `prompts/note-v1.md`,
`prompts/insight-v1.md`. The model reads and phrases only; arithmetic, matching and statuses are deterministic
Python (see `CLAUDE.md`).

## Configuration files

| Category | Path | Status |
|---|---|---|
| Agent instructions / rules | `CLAUDE.md` | used |
| Subagents | `.claude/agents/implementer.md`, `.claude/agents/reviewer.md` | used |
| Skills | `.claude/skills/generate-assignment-data/SKILL.md` | used (Phase 6) |
| Skills | `.claude/skills/verify-reconciliation/SKILL.md` | not-used: kept unchanged; it refers to `scripts/eval.py`, a 98% accuracy gate and ruff/mypy, which do not exist in this project, and the loop did not use it |
| Design docs and loop state | `docs/SPEC.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `PLAN.md`, `DATASET.md`, `REVIEW_CHECKLIST.md`, `PROGRESS.md` | used |
| Application prompts | `prompts/*.md` | used |
| Business rules | `data/inputs/domain.md` (read-only, supplied) | used |
| Hooks | none | not-used |
| MCP / tool settings | none | not-used |
| Permissions | none beyond Claude Code defaults | default |
| Review baseline script | `tools/baseline.py` (manual copy to `.baseline/`, replaces git for reviews; not a hook) | not-used as automation |
| Environment names | `.env.example`, `ai-workflow/.env.example` (names only) | redacted |

**Redactions:** the `GEMINI_API_KEY` value and the other local values in `.env` are not included; the real `.env`
is gitignored and not part of the submission. No user-level Claude Code configuration was copied.

**Versions.** The files are the current versions. Earlier versions of changed configuration files are kept as named
snapshots in `ai-workflow/snapshots/` (`ARCHITECTURE.md.phase3.md`, `ARCHITECTURE.md.phase4.md`,
`DECISIONS.md.phase3.md`, `DECISIONS.phase7.md`, `DECISIONS.md.phase-8.md`, `PLAN.md.phase-8.md`). Every configuration
change and its reason are recorded in `workflow-log.md`. Each phase review is saved in
`ai-workflow/reviews/phase-<n>-round-<m>.md`.

**Restore.** Project configuration is in its normal location: copy `CLAUDE.md` and `.claude/` into a repository
root and Claude Code picks them up. The loop is described in `CLAUDE.md`; there are no hooks to enable.

## One workflow example

- **Instruction:** run Phase 3 (storage, pipeline, CLI) through the implement, test, review loop.
- **Configuration that affected it:** `CLAUDE.md` (rules and loop), the `implementer` and `reviewer` subagents,
  `docs/PLAN.md` Phase 3 and `docs/DECISIONS.md`.
- **Check:** `MODEL_MODE=replay pytest -q` (84 tests at that point), then an independent review (round 1: PASS,
  two minors deferred).
- **Correction:** the end-to-end replay run made all four seed invoices `invalid`, because decision A12 required a
  line description and the seed images print none. The implementer stopped and asked instead of deciding. The user
  chose to allow a null description; A12 and `ARCHITECTURE.md` were changed, the check was removed from
  `normalize.py`, and the earlier files were saved under `ai-workflow/snapshots/`.
- **Where recorded:** `workflow-log.md`, entries "2026-10-08 20:30 - Phase 3 decision: A12 revised" and
  "2026-10-08 20:45 - Phase 3 storage, pipeline, CLI". Other catches by review are in `ai-workflow/reviews/`
  (for example the Phase 4 round 1 finding that the UI failed on an older Streamlit).

Relevant excerpt of the number-guard rule given to the note prompt (`prompts/note-v1.md`): "Use only facts and
amounts that appear in the JSON. Write every amount exactly as given in the JSON, in the form $X.XX. Do not add,
subtract, convert, round or total any numbers."

## Reproduce or replay

Requirements: Python 3.11+ (developed on 3.12.10), `pip install -r requirements.txt` (pinned versions). No API key
is needed; `MODEL_MODE` defaults to `replay` and reads the saved real responses in `data/model_cache/`.

```bash
MODEL_MODE=replay pytest -q
MODEL_MODE=replay python -m invoice_recon.cli run
streamlit run app/streamlit_app.py
```

PowerShell: `$env:MODEL_MODE="replay"; python -m pytest -q`. Live calls need `GEMINI_API_KEY`, `GEMINI_MODEL` and
`MODEL_MODE=live` in `.env` (see the main README). There are no hooks: nothing runs automatically when files
change or a session starts.

## Decisions and limitations

- The setup suited the task because the rules (`CLAUDE.md`) keep the model to reading and phrasing, and the
  separate read-only reviewer plus saved review files give evidence that results were checked independently of the
  implementer. Expected values come from `domain.md`, the seed files and `scripts/compute_expected.py`, never from
  application output.
- Limitations: the `verify-reconciliation` skill is a leftover that does not fit this project (kept, marked
  `not-used`); `docs/DECISIONS.md` D6 originally said "no subagents" and was corrected in Phase 8 (snapshot kept);
  the Claude Code version and orchestrator model were stated by the author, not exported by a tool; earlier states of changed files exist only as the
  listed snapshots and the saved reviews.
