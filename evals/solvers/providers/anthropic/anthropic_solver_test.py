import os

import pytest
from anthropic.types import Message as AnthropicMessage
from anthropic.types import Usage

from evals.record import DummyRecorder
from evals.solvers.providers.anthropic.anthropic_solver import AnthropicSolver, anth_to_openai_usage
from evals.task_state import Message, TaskState

IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"
MODEL_NAME = "claude-instant-1.2"


@pytest.fixture
def anthropic_solver():
    solver = AnthropicSolver(
        model_name=MODEL_NAME,
    )
    return solver


@pytest.fixture
def dummy_recorder():
    """
    Sets the "default_recorder" necessary for sampling in the solver.
    """
    recorder = DummyRecorder(None)  # type: ignore
    with recorder.as_default_recorder("x"):
        yield recorder


@pytest.mark.skipif(IN_GITHUB_ACTIONS, reason="API tests are wasteful to run on every commit.")
def test_solver(dummy_recorder, anthropic_solver):
    """
    Test that the solver generates a response coherent with the message history
    while following the instructions from the task description.
    - checks the task description is understood
    - checks that the messages are understood
    """
    solver = anthropic_solver

    answer = "John Doe"
    task_state = TaskState(
        task_description=f"When you are asked for your name, respond with '{answer}' (without quotes).",
        messages=[
            Message(role="user", content="What is 2 + 2?"),
            Message(role="assistant", content="4"),
            Message(role="user", content="What is your name?"),
        ],
    )

    solver_res = solver(task_state=task_state)
    assert solver_res.output == answer, f"Expected '{answer}', but got {solver_res.output}"


def test_message_format():
    """
    Test that messages in our evals format are correctly
    converted to the format expected by Anthropic
    - "system" messages mapped to "user" in Anthropic
    - messages must alternate between "user" and "assistant"
    - messages are plain dicts in the shape the Messages API accepts
    """
    msgs = [
        Message(role="user", content="What is 2 + 2?"),
        Message(role="system", content="reason step by step"),
        Message(role="assistant", content="I don't need to reason for this, 2+2 is just 4"),
        Message(role="system", content="now, given your reasoning, provide the answer"),
    ]
    anth_msgs = AnthropicSolver._convert_msgs_to_anthropic_format(msgs)

    def text(t):
        return {"type": "text", "text": t}

    expected = [
        {"role": "user", "content": [text("What is 2 + 2?"), text("reason step by step")]},
        {
            "role": "assistant",
            "content": [text("I don't need to reason for this, 2+2 is just 4")],
        },
        {"role": "user", "content": [text("now, given your reasoning, provide the answer")]},
    ]

    assert anth_msgs == expected, f"Expected {expected}, but got {anth_msgs}"


def test_anth_to_openai_usage_correctness():
    usage = Usage(input_tokens=100, output_tokens=150)
    expected = {
        "completion_tokens": 150,
        "prompt_tokens": 100,
        "total_tokens": 250,
    }
    assert (
        anth_to_openai_usage(usage) == expected
    ), "The conversion does not match the expected format."


def test_anth_to_openai_usage_zero_tokens():
    usage = Usage(input_tokens=0, output_tokens=0)
    expected = {
        "completion_tokens": 0,
        "prompt_tokens": 0,
        "total_tokens": 0,
    }
    assert anth_to_openai_usage(usage) == expected, "Zero token cases are not handled correctly."


def test_solver_against_a_stubbed_client(dummy_recorder, monkeypatch):
    """Exercise the solver's request and response handling without a network call or key."""
    captured = {}

    class StubMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return AnthropicMessage.model_validate(
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "model": kwargs["model"],
                    "content": [{"type": "text", "text": "4"}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                }
            )

    class StubClient:
        messages = StubMessages()

    monkeypatch.setattr(
        "evals.solvers.providers.anthropic.anthropic_solver.Anthropic", lambda **_: StubClient()
    )

    solver = AnthropicSolver(model_name="test-model", max_tokens=16)
    task_state = TaskState(
        task_description="Answer with a number only.",
        messages=[Message(role="user", content="What is 2 + 2?")],
    )
    result = solver(task_state=task_state)

    assert result.output == "4"
    assert captured["model"] == "test-model"
    assert captured["max_tokens"] == 16
    assert captured["system"] == "Answer with a number only."
    assert captured["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "What is 2 + 2?"}]}
    ]
