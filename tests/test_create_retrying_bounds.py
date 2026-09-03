import importlib.util
import time
from pathlib import Path

import pytest


def _load_api_utils():
    path = Path(__file__).resolve().parents[1] / "evals" / "utils" / "api_utils.py"
    spec = importlib.util.spec_from_file_location("evals_api_utils", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_retrying_gives_up_instead_of_looping_forever(monkeypatch):
    api_utils = _load_api_utils()
    monkeypatch.setattr(api_utils, "EVALS_API_RETRY_MAX_TIME", 0.2)
    # Avoid real sleeps during exponential backoff.
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)

    attempts = {"n": 0}

    def always_fail():
        attempts["n"] += 1
        raise ConnectionError("boom")

    started = time.monotonic()
    with pytest.raises(ConnectionError):
        api_utils.create_retrying(always_fail, retry_exceptions=(ConnectionError,))
    elapsed = time.monotonic() - started

    assert attempts["n"] >= 2
    assert elapsed < 5.0
