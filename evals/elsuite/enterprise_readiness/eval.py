"""Enterprise readiness: grounded policy Q&A with structured, cited answers.

The solver gets a small set of (fictional) company security and data protection
policies and answers employee questions as a JSON object. The eval checks four
things an enterprise buyer cares about: the reply is machine-readable, it is
grounded in the right policy sections, it says "not covered" instead of
guessing, and it ignores instructions smuggled in through quoted text.
"""

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import numpy as np

from evals.elsuite.enterprise_readiness import grading, prompts
from evals.eval import SolverEval
from evals.record import RecorderBase, record_metrics
from evals.solvers.solver import Solver
from evals.task_state import Message, TaskState

DATA_DIR = Path(__file__).parent / "data"
SAMPLE_TYPES = ("grounded_qa", "scenario", "unanswerable", "injection")


def load_policies(path: Path = DATA_DIR / "policies.json") -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_samples(path: Path = DATA_DIR / "samples.jsonl") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def render_policies(policies: dict) -> str:
    blocks = []
    for policy in policies["policies"]:
        lines = [f"## {policy['title']}"]
        lines += [f"[{s['id']}] {s['title']}: {s['text']}" for s in policy["sections"]]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def section_ids(policies: dict) -> set[str]:
    return {s["id"].upper() for p in policies["policies"] for s in p["sections"]}


class EnterpriseReadiness(SolverEval):
    def __init__(
        self,
        samples_path: Optional[str] = None,
        policies_path: Optional[str] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.policies = load_policies(Path(policies_path)) if policies_path else load_policies()
        self.samples_path = Path(samples_path) if samples_path else DATA_DIR / "samples.jsonl"
        self.valid_ids = section_ids(self.policies)
        self.task_description = prompts.TASK_DESCRIPTION.format(
            company=self.policies["company"], policies=render_policies(self.policies)
        )

    def eval_sample(self, solver: Solver, sample: dict, rng: random.Random) -> None:
        task_state = TaskState(
            task_description=self.task_description,
            messages=[
                Message(
                    role="user",
                    content=prompts.QUESTION_TEMPLATE.format(question=sample["question"]),
                )
            ],
        )
        output = solver(task_state).output
        result = grading.grade(output, sample["expected"], self.valid_ids)
        record_metrics(sample_id_str=sample["id"], sample_type=sample["type"], **result)

    def run(self, recorder: RecorderBase) -> dict[str, Any]:
        samples = load_samples(self.samples_path)
        self.eval_all_samples(recorder, samples)
        return aggregate(recorder.get_metrics())


def _mean(values: list) -> Optional[float]:
    values = [v for v in values if v is not None]
    return float(np.mean(values)) if values else None


def aggregate(rows: list[dict]) -> dict[str, Any]:
    """Roll per-sample results up into the reported metrics."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_type[row["sample_type"]].append(row)
    answerable = [r for r in rows if r["sample_type"] != "unanswerable"]

    metrics: dict[str, Any] = {
        "accuracy": _mean([r["correct"] for r in rows]),
        "json_valid_rate": _mean([r["json_valid"] for r in rows]),
        "schema_valid_rate": _mean([r["schema_valid"] for r in rows]),
        "hallucinated_citation_rate": _mean([r["hallucinated_citation"] for r in rows]),
        "citation_recall": _mean([r["citation_recall"] for r in answerable]),
        "citation_precision": _mean([r["citation_precision"] for r in answerable]),
        # Said "not covered" when the policies did answer it.
        "false_abstention_rate": _mean(
            [r["schema_valid"] and not r["answerable_correct"] for r in answerable]
        ),
        "verdict_accuracy": _mean([r["verdict_correct"] for r in rows]),
    }
    for sample_type in SAMPLE_TYPES:
        metrics[f"accuracy_{sample_type}"] = _mean([r["correct"] for r in by_type[sample_type]])
    metrics["n_samples"] = len(rows)
    return metrics
