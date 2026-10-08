# Invoice Reconciliation & Review Platform

> Junior AI Engineer take-home — Alternative B. All people, businesses, transactions and policies are fictional.
> _Skeleton: Claude Code fills in each section as the phases are completed (see `docs/PLAN.md`)._

## Overview
<!-- What the app does in 3–5 sentences; screenshot of the review queue. -->

## Quick start (no API key needed)
Phase 0 is complete: configuration and the repository scaffold are available.
The CLI, UI, prompts, and generated datasets are placeholders for later phases.
The root planning documents are preserved; `docs/` contains their setup copies.

Windows PowerShell setup and check:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
```

Activation is optional: use `.\.venv\Scripts\python.exe` directly if needed.
The requirements install the local `src/` package in editable mode.
`.env.example` lists names only; blank or unset `MODEL_MODE` defaults to `replay`,
and blank or unset `USE_SIMULATIONS` defaults to `1`. Existing environment
variables take precedence over the root `.env` file.

Full application commands (available in later phases):
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # MODEL_MODE=replay by default
python -m invoice_recon.cli run
streamlit run app/streamlit_app.py
pytest
```

## Running with live model calls
<!-- GEMINI_API_KEY, GEMINI_MODEL, MODEL_MODE=live; what gets written to data/model_cache/. -->

## Replaying saved real responses
<!-- How replay works, cache key, provenance labels (live / cached / simulated), simulated failures. -->

## Architecture
<!-- Pipeline diagram and module overview; link docs/ARCHITECTURE.md. -->

## Model configuration
<!-- Provider, model ID, temperature, response schema, max output tokens, retries, prompt versions. -->

## Business rules, rounding and statuses
<!-- Link data/inputs/domain.md. Rounding rule: integer cents, Decimal parsing, >2 decimals rejected, never rounded. Status precedence. -->

## Data
<!-- Seed vs generated data, generation method, mapping from template to lines format, processing order and duplicate rule. -->

## Reference cases and check results
<!-- The five reference cases (M1–M5), how expected values were verified, link reports/check-results.md, any failures explained. -->

## Decisions and unresolved ambiguity
<!-- Summary of docs/DECISIONS.md, especially the ambiguity table A1–A10. -->

## Known limitations
<!-- e.g. one PO per invoice, single currency, small demonstration set gives limited evidence of accuracy. -->

## Time spent
| Phase | Time |
|---|---|
| | |

## LLM usage note
<!-- Development tools and models, generated components, one representative instruction, one correction/verification. Details in ai-workflow/. -->

## AI configuration
See `ai-workflow/README.md` and `ai-workflow/manifest.json`.

## Presentation
<!-- Link to recording, slides or written walkthrough. -->
