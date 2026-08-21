import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("OPENAI_API_KEY", "dummy")

import evals.eval
from evals.cli.oaieval import run


def test_run_without_max_samples_clears_previous_in_process_limit(monkeypatch) -> None:
    monkeypatch.setattr(evals.eval, "_MAX_SAMPLES", 1)

    args = SimpleNamespace(
        debug=False,
        visible=None,
        max_samples=None,
        registry_path=None,
        eval="missing-eval",
    )
    registry = MagicMock()
    registry.get_eval.return_value = None
    registry._evals = {}

    # The missing eval stops the run immediately after per-run setup. That is
    # enough to verify that an uncapped invocation clears stale global state.
    with pytest.raises(AssertionError, match="Eval missing-eval not found"):
        run(args, registry=registry)

    assert evals.eval._MAX_SAMPLES is None


def test_run_sets_current_max_samples_before_registry_lookup(monkeypatch) -> None:
    monkeypatch.setattr(evals.eval, "_MAX_SAMPLES", None)

    args = SimpleNamespace(
        debug=False,
        visible=None,
        max_samples=7,
        registry_path=None,
        eval="missing-eval",
    )
    registry = MagicMock()
    registry.get_eval.return_value = None
    registry._evals = {}

    with pytest.raises(AssertionError, match="Eval missing-eval not found"):
        run(args, registry=registry)

    assert evals.eval._MAX_SAMPLES == 7
