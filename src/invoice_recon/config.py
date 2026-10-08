"""Repository paths and environment configuration; replay requires no API key."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
INPUTS_DIR = DATA_DIR / "inputs"
GENERATED_DIR = DATA_DIR / "generated"
MODEL_CACHE_DIR = DATA_DIR / "model_cache"
STATE_DIR = DATA_DIR / "state"
PROMPTS_DIR = ROOT_DIR / "prompts"
SIMULATIONS_PATH = DATA_DIR / "simulations.json"

load_dotenv(ROOT_DIR / ".env", override=False)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip()
MODEL_MODE = os.getenv("MODEL_MODE", "").strip() or "replay"
if MODEL_MODE not in {"live", "replay"}:
    raise ValueError("MODEL_MODE must be live or replay")

_simulations = os.getenv("USE_SIMULATIONS", "").strip() or "1"
if _simulations not in {"0", "1"}:
    raise ValueError("USE_SIMULATIONS must be 0 or 1")
USE_SIMULATIONS = _simulations == "1"
SIMULATED_FAILURES = frozenset(
    value.strip()
    for value in os.getenv("SIMULATED_FAILURES", "").split(",")
    if value.strip()
)

EXTRACT_PROMPT_VERSION = "extract-v1"
NOTE_PROMPT_VERSION = "note-v1"
INSIGHT_PROMPT_VERSION = "insight-v1"
