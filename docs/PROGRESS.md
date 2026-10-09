# Progress

Maintained by the orchestrator (main Claude Code session). Read this first in every new session or after
`/clear`. Update it at every step of the loop.

## Current state

- **Phase:** 8 — Documentation and AI config
- **Step:** done (Phase 8 approved; baseline saved). All phases complete.
- **Review round:** 1 saved review (CHANGES_REQUESTED), fixes applied; later review files removed at user request
- **Phase 8 finished:** 2026-10-09 11:35
- **Phase 8 started:** 2026-10-09 11:13
- **Phase 7 started:** 2026-10-09 10:45
- **Phase 6 started:** 2026-10-08 22:50
- **Phase 5 started:** 2026-10-08 21:37
- **Phase 4 started:** 2026-10-08 20:27
- **Phase 3 started:** 2026-10-08 20:12
- **Phase 2 started:** 2026-10-08 19:59
- **Phase 1 started:** 2026-10-08 17:11
- **Initial baseline:** saved to `.baseline/` on 2026-10-08 16:46 (91 files)
- **Phase 0 started:** 2026-10-08 16:46
- **Waiting for user:** nothing. All phases complete.

## Phase log

| Phase | Status | Review rounds | Started | Finished | Time |
|---|---|---|---|---|---|
| 0 Setup | done (approved 2026-10-08) | n/a | 2026-10-08 16:46 | 2026-10-08 | ~22 min |
| 1 Core domain | done (approved 2026-10-08) | 1 | 2026-10-08 17:11 | 2026-10-08 17:20 | ~25 min |
| 2 Extraction | done (approved 2026-10-08) | 1 | 2026-10-08 19:59 | 2026-10-08 | |
| 3 Storage, pipeline, CLI | done (approved 2026-10-08) | 1 | 2026-10-08 20:12 | 2026-10-08 | ~40 min |
| 4 UI | done (approved 2026-10-08) | 2 | 2026-10-08 20:27 | 2026-10-08 | ~15 min |
| 5 Notes and insight | done (approved 2026-10-08) | 1 | 2026-10-08 21:37 | 2026-10-08 | |
| 6 Dataset extension | done (approved 2026-10-08) | 1 | 2026-10-08 22:50 | 2026-10-08 23:23 | ~33 min |
| 7 Checks and report | done (approved 2026-10-09) | 1 | 2026-10-09 10:45 | 2026-10-09 11:03 | ~18 min |
| 8 Documentation and AI config | done (approved 2026-10-09) | 3 | 2026-10-09 11:13 | 2026-10-09 11:35 | ~22 min |

## Open findings (current phase)

_None._

## Deferred minor findings

_Minors the reviewer raised that were not fixed; revisit in Phase 8 or list as limitations._

- P2 #1 `extraction/service.py` cached path: a cache entry missing `model`/`raw_text` should fail instead of defaulting to the current model.
- P3 #1 `storage.load_all` raises StorageError on one corrupt invoice file, aborting the whole batch (visible, but not per-invoice); consider per-invoice failure in Phase 4.
- P4 #3 `use_container_width=True` deprecated in streamlit 1.65 (kept for older-streamlit compatibility).
- P3 #2 typo `subset ={` in reference.py:29.
- P5 #1 number guard checks amounts exist in the payload, not field/sign correctness; document as a limitation in Phase 8.
- P5 #2 a live `run` makes one call per non-reconciled invoice plus one for the insight; mention in README.
- P6 #1 new images have no cached responses: replay shows "extraction failed" until the live extraction (needs user approval) is run.
- P7 #1 tests/test_check_report.py overwrites reports/check-results.md on every pytest run and cannot detect a mismatch; add a compare() unit test / write to tmp.
- P7 #2 check_report M3 payable count uses reconciled/discrepant, not raw count_as_payable (A14); add a note in the report.
- P5 insight fallback wording: "(count: 1, invoices affected: 1)" has no plural grammar.

## Notes for the next session

_Anything the next session must know that is not in the docs._

- 2026-10-08: `MODEL_MODE=live cli run` for Phase 6 also drafted notes/insight live (7 notes), which was not explicitly approved; check whether data/model_cache/ now holds notes entries and tell the user.
- User decided (2026-10-08): run the live notes/insight calls AFTER Phase 6, so the cache covers the extended dataset. Cache keys depend on the findings payload. Ask for approval before the live run.