"""Exercise configuration without reading local secrets or calling a model."""

import runpy
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parents[1] / "src/invoice_recon/config.py"


def test_configuration(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    for name in ("MODEL_MODE", "USE_SIMULATIONS", "SIMULATED_FAILURES", "GEMINI_API_KEY", "GEMINI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    settings = runpy.run_path(str(CONFIG))
    assert settings["ROOT_DIR"] == CONFIG.parents[2]
    assert settings["INPUTS_DIR"].joinpath("seed.json").is_file()
    assert settings["MODEL_MODE"] == "replay"
    assert settings["USE_SIMULATIONS"] is True
    assert settings["GEMINI_API_KEY"] == ""

    monkeypatch.setenv("MODEL_MODE", "live")
    monkeypatch.setenv("USE_SIMULATIONS", "0")
    monkeypatch.setenv("SIMULATED_FAILURES", " clean, , duplicate, clean ")
    settings = runpy.run_path(str(CONFIG))
    assert settings["MODEL_MODE"] == "live"
    assert settings["USE_SIMULATIONS"] is False
    assert settings["SIMULATED_FAILURES"] == {"clean", "duplicate"}

    monkeypatch.setenv("MODEL_MODE", "")
    monkeypatch.setenv("USE_SIMULATIONS", "")
    assert runpy.run_path(str(CONFIG))["MODEL_MODE"] == "replay"
    for name in ("MODEL_MODE", "USE_SIMULATIONS"):
        monkeypatch.setenv(name, "invalid")
        with pytest.raises(ValueError, match=name):
            runpy.run_path(str(CONFIG))
        monkeypatch.setenv(name, "")
