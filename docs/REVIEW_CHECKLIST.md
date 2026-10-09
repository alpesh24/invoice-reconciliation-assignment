# Review checklist

Used by the `reviewer` subagent for every phase from Phase 1 on. There is no git: the baseline is the
`.baseline/` copy saved after the last approved phase. `python tools/baseline.py status [path]` lists
added (`A`), modified (`M`) and deleted (`D`) files; `python tools/baseline.py diff [path]` shows a
unified diff. Commands assume bash (Git Bash on Windows).
A check that does not apply yet (e.g. no `app/` before Phase 4) is reported as `n/a`.

## Mechanical checks

Commands are in code blocks (not tables) so they can be copied exactly.

**K1 — Starter inputs untouched.** Pass: output empty.
```bash
python tools/baseline.py status data/inputs/
```

**K2 — Tests green without a key.** Pass: all tests pass.
```bash
env -u GEMINI_API_KEY MODEL_MODE=replay pytest -q
```

**K3 — No answer-key access from the app.** Pass: no hits.
```bash
grep -rnE "\[\s*['\"]invoices['\"]\s*\]|get\(\s*['\"]invoices['\"]|expected-seed-results|expected-results|invoice-records|invoice\.template|data/expected" src/ app/
```

**K4 — No float or rounding in money logic.** Pass: no hits, or a hit that is clearly not money (explain).
```bash
grep -nE "float|round\(" src/invoice_recon/money.py src/invoice_recon/normalize.py src/invoice_recon/matching.py src/invoice_recon/reconcile.py
```

**K5 — No fuzzy matching.** Pass: no hits used on IDs or SKUs.
```bash
grep -rniE "difflib|fuzz|levenshtein|similar|distance|\.lower\(|\.upper\(|casefold|startswith" src/invoice_recon/matching.py src/invoice_recon/normalize.py
```

**K6 — Model calls only where allowed.** Pass: only files under `src/invoice_recon/extraction/`, `notes.py`, `insights.py`.
```bash
grep -rlE "genai|generate_content" src/ app/
```

**K7 — No secrets outside `.env`.** Pass: `.gitignore` lists `.env` and `.baseline/`; the key search finds nothing.
```bash
grep -nxE "\.env|\.baseline/?" .gitignore    # must list both
grep -rnE "AIza[0-9A-Za-z_-]{20,}" . --exclude=.env --exclude-dir=.venv --exclude-dir=.baseline
```

**K8 — Tests not weakened.** Pass: no hits, or each hit justified.
```bash
python tools/baseline.py diff tests/ | grep -nE "^-\s*assert|^\+.*(pytest\.mark\.skip|xfail|pytest\.skip)"
```

**K9 — Used prompts not edited in place.** Pass: no `M` (modified) or `D` (deleted) prompt files; new prompt versions appear as `A`.
```bash
python tools/baseline.py status prompts/
```

**K10 — No business logic in the UI.** Read `app/`. Pass: the UI calls `pipeline` / `storage` only; no arithmetic, matching or status logic.

## Rule checks (CLAUDE.md non-negotiable rules)

- [ ] **Rule 1** — no business rule beyond `domain.md` and `DECISIONS.md`; ambiguities went to "Open questions".
- [ ] **Rule 2** — cents are `int`; parsing uses `Decimal`; > 2 decimals is an error, not rounded.
- [ ] **Rule 3** — the model never computes; extraction returns strings as printed.
- [ ] **Rule 4** — invoice→PO by exact `(supplier_id, po_id)`; lines by exact SKU within the matched PO;
      missing/conflicting/ambiguous → `unresolved`, with `expected_cents`/`difference_cents` = `null`.
- [ ] **Rule 6/7** — expected values in tests and `data/expected/` are independent of the application.
- [ ] **Rule 8** — raw extraction is never overwritten; corrections are an overlay with history.
- [ ] **Rule 9** — one failing document cannot stop the batch; failure is a visible status.
- [ ] **Rule 10** — every model result carries `source = live | cached | simulated`.
- [ ] **Rule 12** — note prompts and outputs are drafts with neutral wording.

## Logic spot checks (when the phase touches reconciliation)

- [ ] Status precedence matches ARCHITECTURE.md (failed → invalid → duplicate → unresolved → discrepant → reconciled).
- [ ] Duplicate decided by `ingest_seq`, never by file name, image hash or disk order alone.
- [ ] Expected = ordered qty × agreed unit price from the **matched PO line** (not a global SKU price).
- [ ] `recoverable_cents` counts only positive differences of `discrepant` invoices.
- [ ] Hand-recompute at least one case, e.g. wrong-price: expected 5 × 2000 = 10000, billed 12000, diff +2000.

## Test quality

- [ ] Tests cover the behavior the phase requires (see PLAN.md), including the failure paths.
- [ ] Assertions use concrete expected values, not values produced by the code under test.
- [ ] Tests are deterministic and make no network calls.

## Scope

- [ ] Only the current phase was implemented; no optional features before M1–M5 pass.
- [ ] New dependencies are pinned in `requirements.txt` and justified.
- [ ] Phase checkpoint from PLAN.md is met.