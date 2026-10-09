# Phase 2 — Review round 1

PHASE: 2  ROUND: 1  BASE: .baseline/
VERDICT: PASS
MECHANICAL CHECKS:
- K1 pass; K2 pass (69 passed, venv python, GEMINI_API_KEY unset, MODEL_MODE=replay); K3 pass; K4 n/a; K5 n/a;
  K6 pass (only extraction/gemini.py); K7 pass; K8 pass; K9 pass (extract-v1.md was a placeholder, no cache entries); K10 n/a.
CHECKPOINT: not met, as expected. data/model_cache/ is empty because the live run is pending. Mechanism tested:
replay reads cache, never calls the model, fails visibly on a miss; cache-hit and live-then-replay tests pass.
FINDINGS:
- #1 [minor] src/invoice_recon/extraction/service.py:~60 — Rule 10 — cached path takes `model` from
  `entry.get("model", model)`, so a malformed cache entry silently reports the current model. Low risk (cache is
  app-written). Optionally fail when `model` or `raw_text` is absent.
NOTES: Rule 9 holds (every per-document failure becomes a `failed` result). Rule 10 holds. Required PLAN tests present.
Invalid JSON from a live call is not cached. Still needed after the live run: eyeball the four responses against the
images, record in the workflow log, re-check replay checkpoint with `python scripts/extract_images.py`.

(Saved by orchestrator; condensed from the reviewer's hand-back, verdict and findings unchanged.)
