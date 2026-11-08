import json
from pathlib import Path

import pytest

from evals.base import RunSpec
from evals.elsuite.enterprise_readiness import grading
from evals.elsuite.enterprise_readiness.eval import (
    SAMPLE_TYPES,
    EnterpriseReadiness,
    load_policies,
    load_samples,
    section_ids,
)
from evals.record import DummyRecorder
from evals.solvers.solver import DummySolver, Solver, SolverResult
from evals.task_state import TaskState

POLICIES = load_policies()
SAMPLES = load_samples()
VALID_IDS = section_ids(POLICIES)


def reply(**overrides) -> str:
    body = {"answerable": True, "answer": "", "citations": [], "verdict": None}
    body.update(overrides)
    return json.dumps(body)


def ideal_reply(expected: dict) -> str:
    answer = " and ".join(group[0] for group in expected["required"]) or "See the cited section."
    return reply(
        answerable=expected["answerable"],
        answer=answer,
        citations=expected["citations"],
        verdict=expected["verdict"],
    )


# --- dataset -----------------------------------------------------------------


def test_sample_ids_are_unique():
    ids = [s["id"] for s in SAMPLES]
    assert len(ids) == len(set(ids))


def test_every_sample_type_is_known_and_covered():
    types = {s["type"] for s in SAMPLES}
    assert types == set(SAMPLE_TYPES)


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s["id"])
def test_expected_answers_are_well_formed(sample):
    expected = sample["expected"]
    cited = set(expected["citations"]) | set(expected["optional_citations"])
    assert cited <= VALID_IDS, f"{sample['id']} cites a section that doesn't exist"
    assert expected["verdict"] in (None, "compliant", "non_compliant")
    if expected["answerable"]:
        assert expected["citations"], "answerable samples need at least one citation"
        assert expected["required"] or expected["verdict"], "nothing to grade the answer on"
    else:
        assert not expected["citations"] and not expected["required"]
    if expected["verdict"] is not None:
        assert "compliant" in sample["question"].lower()


# --- parsing and schema ------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        '{"answerable": true, "answer": "x", "citations": [], "verdict": null}',
        '```json\n{"answerable": true, "answer": "x", "citations": [], "verdict": null}\n```',
        'Here you go: {"answerable": true, "answer": "x", "citations": [], "verdict": null} Thanks',
    ],
)
def test_parse_response_finds_the_object(text):
    assert grading.parse_response(text)["answer"] == "x"


@pytest.mark.parametrize("text", ["", "not json", "[1, 2]", "{broken", None])
def test_parse_response_rejects_non_objects(text):
    assert grading.parse_response(text) is None


def test_schema_errors_catch_wrong_types():
    errors = grading.schema_errors(
        {"answerable": "yes", "answer": 3, "citations": "AC-1", "verdict": "maybe"}
    )
    assert len(errors) == 4
    assert grading.schema_errors({"answerable": True, "answer": "", "citations": []}) == [
        "verdict is missing"
    ]


def test_phrase_match_respects_word_and_number_boundaries():
    assert grading.phrase_present("14", "at least 14 characters")
    assert not grading.phrase_present("14", "at least 140 characters")
    assert grading.phrase_present("AES-256", "uses aes‑256")
    assert grading.phrase_present("72 hours", "within 72  hours")
    assert grading.phrase_present("security key", "hardware security keys")
    assert grading.phrase_present("compromise", "if it is compromised")
    assert not grading.phrase_present("must", "mustard")


# --- grading -----------------------------------------------------------------


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s["id"])
def test_ideal_reply_scores_correct(sample):
    result = grading.grade(ideal_reply(sample["expected"]), sample["expected"], VALID_IDS)
    assert result["correct"], result


def _sample(sample_id):
    return next(s for s in SAMPLES if s["id"] == sample_id)


def test_missing_citation_is_not_correct():
    expected = _sample("gq-17")["expected"]  # needs DP-2 and DP-3
    result = grading.grade(reply(answer="up to 65 days", citations=["DP-3"]), expected, VALID_IDS)
    assert result["answer_correct"] and not result["correct"]
    assert result["citation_recall"] == 0.5


def test_invented_section_is_flagged():
    expected = _sample("in-02")["expected"]
    result = grading.grade(
        reply(answer="35 days", citations=["DP-3", "DP-99"]), expected, VALID_IDS
    )
    assert result["hallucinated_citation"] and not result["correct"]


def test_wrong_verdict_is_not_correct():
    expected = _sample("sc-01")["expected"]
    result = grading.grade(
        reply(answer="Fine.", citations=["AC-4"], verdict="compliant"), expected, VALID_IDS
    )
    assert result["verdict_correct"] is False and not result["correct"]


def test_abstaining_on_a_covered_question_is_wrong():
    expected = _sample("gq-04")["expected"]
    result = grading.grade(reply(answerable=False, answer="Not covered."), expected, VALID_IDS)
    assert not result["answerable_correct"] and not result["correct"]


def test_guessing_on_an_uncovered_question_is_wrong():
    expected = _sample("un-02")["expected"]
    result = grading.grade(reply(answer="Yes, since 2024."), expected, VALID_IDS)
    assert not result["correct"]
    result = grading.grade(reply(answerable=False, answer="Not covered."), expected, VALID_IDS)
    assert result["correct"]


def test_unparseable_reply_scores_zero():
    result = grading.grade("The minimum is 14 characters.", _sample("gq-04")["expected"], VALID_IDS)
    assert not result["json_valid"] and not result["correct"]


# --- end to end --------------------------------------------------------------


class OracleSolver(Solver):
    """Answers every sample perfectly by looking up its expected answer."""

    def __init__(self):
        super().__init__()
        self.by_question = {s["question"]: s["expected"] for s in SAMPLES}

    def _solve(self, task_state: TaskState, **kwargs) -> SolverResult:
        question = task_state.messages[-1].content.removeprefix("Question: ")
        return SolverResult(ideal_reply(self.by_question[question]))


def run_eval(solver: Solver) -> dict:
    eval_ = EnterpriseReadiness(
        completion_fns=[solver],
        eval_registry_path=Path("evals/registry"),
        name="enterprise-readiness.dev.v0",
    )
    run_spec = RunSpec(
        completion_fns=[type(solver).__name__],
        eval_name="enterprise-readiness.dev.v0",
        base_eval="enterprise-readiness",
        split="dev",
        run_config={},
        created_by="test",
    )
    recorder = DummyRecorder(run_spec=run_spec, log=False)
    return eval_.run(recorder)


def test_task_description_includes_every_section():
    eval_ = EnterpriseReadiness(
        completion_fns=[DummySolver()],
        eval_registry_path=Path("evals/registry"),
        name="enterprise-readiness.dev.v0",
    )
    for section_id in VALID_IDS:
        assert f"[{section_id}]" in eval_.task_description


def test_oracle_scores_perfectly():
    metrics = run_eval(OracleSolver())
    assert metrics["n_samples"] == len(SAMPLES)
    assert metrics["accuracy"] == 1.0
    assert metrics["hallucinated_citation_rate"] == 0.0
    for sample_type in SAMPLE_TYPES:
        assert metrics[f"accuracy_{sample_type}"] == 1.0


def test_dummy_scores_zero():
    metrics = run_eval(DummySolver())
    assert metrics["accuracy"] == 0.0
    assert metrics["json_valid_rate"] == 0.0
    assert metrics["verdict_accuracy"] == 0.0
