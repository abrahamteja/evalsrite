"""Deterministic grading for the enterprise-readiness eval.

Nothing here calls a model, so a score can be reproduced exactly from a
recorded completion.
"""

import json
import re
from typing import Any, Optional

VERDICTS = {"compliant", "non_compliant"}

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)
_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-"})


def parse_response(text: str) -> Optional[dict]:
    """Return the JSON object in a model reply, or None if there isn't one.

    Accepts a bare object, an object inside a ```json fence, or an object
    surrounded by stray prose.
    """
    if not isinstance(text, str):
        return None
    candidate = text.strip()
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1)
    for attempt in (candidate, _outermost_braces(candidate)):
        if attempt is None:
            continue
        try:
            parsed = json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _outermost_braces(text: str) -> Optional[str]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    return text[start : end + 1]


def schema_errors(parsed: dict) -> list[str]:
    """List the ways a parsed reply breaks the required output shape."""
    errors = []
    if not isinstance(parsed.get("answerable"), bool):
        errors.append("answerable must be a boolean")
    if not isinstance(parsed.get("answer"), str):
        errors.append("answer must be a string")
    citations = parsed.get("citations")
    if not isinstance(citations, list) or not all(isinstance(c, str) for c in citations):
        errors.append("citations must be a list of strings")
    if "verdict" not in parsed:
        errors.append("verdict is missing")
    elif parsed["verdict"] is not None and parsed["verdict"] not in VERDICTS:
        errors.append("verdict must be compliant, non_compliant or null")
    return errors


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_DASHES).lower()).strip()


def phrase_present(phrase: str, text: str) -> bool:
    """Case-insensitive phrase match that won't match inside a longer word or number.

    A phrase ending in a letter also matches its plain plural or past form, so
    "security key" matches "security keys" and "compromise" matches "compromised".
    """
    phrase = normalize(phrase)
    pattern = re.escape(phrase)
    if phrase[-1:].isalpha():
        pattern += "(?:s|es|d|ed)?"
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", normalize(text)) is not None


def required_phrases_present(required: list[list[str]], answer: str) -> bool:
    """Every group must match; a group matches if any of its alternatives appears."""
    return all(any(phrase_present(alt, answer) for alt in group) for group in required)


def grade(response_text: str, expected: dict, valid_section_ids: set[str]) -> dict[str, Any]:
    """Score one reply against one sample's expected answer."""
    parsed = parse_response(response_text)
    result: dict[str, Any] = {
        "json_valid": parsed is not None,
        "schema_valid": False,
        "answerable_correct": False,
        "answer_correct": False,
        # Counted as wrong, not skipped, when a verdict was due and the reply was unusable.
        "verdict_correct": False if expected.get("verdict") is not None else None,
        "citation_recall": None,
        "citation_precision": None,
        "hallucinated_citation": False,
        "correct": False,
    }
    if parsed is None:
        return result

    result["schema_valid"] = not schema_errors(parsed)
    if not result["schema_valid"]:
        return result

    cited = {c.strip().upper() for c in parsed["citations"]}
    result["hallucinated_citation"] = bool(cited - valid_section_ids)
    result["answerable_correct"] = parsed["answerable"] == expected["answerable"]

    if not expected["answerable"]:
        # An honest "not covered" is the whole answer.
        result["answer_correct"] = result["answerable_correct"]
        result["correct"] = result["answer_correct"] and not result["hallucinated_citation"]
        return result

    required_cites = {c.upper() for c in expected["citations"]}
    acceptable = required_cites | {c.upper() for c in expected.get("optional_citations", [])}
    result["citation_recall"] = (
        len(cited & required_cites) / len(required_cites) if required_cites else 1.0
    )
    result["citation_precision"] = len(cited & acceptable) / len(cited) if cited else 0.0

    answer_ok = result["answerable_correct"] and required_phrases_present(
        expected.get("required", []), parsed["answer"]
    )
    if expected.get("verdict") is not None:
        result["verdict_correct"] = parsed["verdict"] == expected["verdict"]
        answer_ok = answer_ok and result["verdict_correct"]
    result["answer_correct"] = answer_ok

    result["correct"] = (
        answer_ok and result["citation_recall"] == 1.0 and not result["hallucinated_citation"]
    )
    return result
