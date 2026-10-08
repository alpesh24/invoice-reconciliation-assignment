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
