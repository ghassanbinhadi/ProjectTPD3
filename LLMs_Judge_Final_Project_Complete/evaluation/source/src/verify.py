"""Build verified datasets and checkpoint metrics from saved interactions.

This module joins Pipeline JSONL records with GSM8K gold answers. It does not
train classifiers or generate policy comparisons.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping

NUMERIC_TOLERANCE = 1e-6
EXPECTED_PILOT_MIN = 40
EXPECTED_PILOT_MAX = 50
FULL_SCALE_INTERACTIONS = (300, 500)

TRANSITIONS = ("HELPED", "HURT", "STABLE-CORRECT", "STABLE-WRONG")

# Keep the output columns ordered so downstream stages receive a stable schema.
DATASET_COLUMNS = (
    "question_id",
    "question",
    "gold_answer",
    "dataset_split",
    "direction",
    "solver_model",
    "critic_model",
    "solver_reasoning",
    "solver_answer",
    "solver_correct",
    "critic_independent_reasoning",
    "critic_independent_answer",
    "critic_independent_correct",
    "critic_solver_agree_before_verdict",
    "critic_verdict",
    "critic_error_desc",
    "critic_proposed_answer",
    "revision_called",
    "revision_reasoning",
    "revise_decision",
    "revised_answer",
    "revised_correct",
    "changed_answer",
    "transition",
    "beneficial",
    "valid",
    "parse_failure_stage",
    "retry_count",
    "split",
    "critic_disagrees",
    "proposed_answer_differs",
    "explicit_error_flag",
    "hedging_count",
    "critique_length",
    "self_consistency",
    "solver_tokens",
    "critic_independent_tokens",
    "critique_tokens",
    "revision_tokens",
    "latency_s",
    "prompt_version",
    "timestamp",
)


class EvaluationValidationError(RuntimeError):
    """Raised when saved Pipeline records cannot support a valid evaluation."""


@dataclass(frozen=True)
class GoldAnswer:
    answer: str
    question: str
    split: str


def _read_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise EvaluationValidationError(f"Invalid JSONL at {path}:{line_number}.") from exc
                if not isinstance(record, dict):
                    raise EvaluationValidationError(f"JSONL record at {path}:{line_number} is not an object.")
                if record.get("record_type") != "pipeline_interaction":
                    raise EvaluationValidationError(
                        f"Unexpected record_type at {path}:{line_number}; expected pipeline_interaction."
                    )
                interaction_id = record.get("interaction_id")
                if not isinstance(interaction_id, str) or not interaction_id:
                    raise EvaluationValidationError(f"Record at {path}:{line_number} has no interaction_id.")
                if interaction_id in seen_ids:
                    raise EvaluationValidationError(
                        f"Duplicate interaction_id {interaction_id!r}; do not combine overlapping JSONL runs."
                    )
                seen_ids.add(interaction_id)
                records.append(record)
    if not records:
        raise EvaluationValidationError("No Pipeline interaction records were found.")
    return records


def _parse_numeric(value: Any, *, context: str) -> str:
    """Normalize permitted formatting and require one numeric value."""
    if not isinstance(value, str):
        raise EvaluationValidationError(f"{context} is missing or is not text.")
    candidate = value.strip()
    if not candidate:
        raise EvaluationValidationError(f"{context} is empty.")
    candidate = re.sub(r"[$\u20ac\u00a3\u00a5]", "", candidate)
    candidate = re.sub(r"[\s,]+", "", candidate).rstrip(".,;:!?")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", candidate):
        raise EvaluationValidationError(f"{context} is not one signed integer or decimal: {value!r}")
    return candidate


def _numeric_equal(left: str | None, right: str | None) -> bool | None:
    if left is None or right is None:
        return None
    return abs(float(left) - float(right)) <= NUMERIC_TOLERANCE


def _stage(record: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    stages = record.get("stages")
    if not isinstance(stages, Mapping):
        return None
    value = stages.get(name)
    return value if isinstance(value, Mapping) else None


def _stage_complete(stage: Mapping[str, Any] | None) -> bool:
    return stage is not None and stage.get("status") == "complete"


def _stage_answer(stage: Mapping[str, Any] | None) -> str | None:
    if not _stage_complete(stage):
        return None
    assert stage is not None
    for key in ("normalized_answer", "answer", "parsed_answer"):
        value = stage.get(key)
        if isinstance(value, str) and value.strip():
            try:
                return _parse_numeric(value, context=f"stage {stage.get('stage', 'answer')} answer")
            except EvaluationValidationError:
                return None
    return None


def _stage_text(stage: Mapping[str, Any] | None, key: str) -> str | None:
    if stage is None:
        return None
    value = stage.get(key)
    return value if isinstance(value, str) else None


def _stage_number(stage: Mapping[str, Any] | None, key: str) -> int | float | None:
    if stage is None:
        return None
    value = stage.get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _stage_tokens(stage: Mapping[str, Any] | None) -> int | None:
    direct = _stage_number(stage, "completion_tokens")
    if isinstance(direct, (int, float)):
        return int(direct)
    if stage is None:
        return None
    attempts = stage.get("attempts")
    if not isinstance(attempts, list):
        return None
    values = [attempt.get("completion_tokens") for attempt in attempts if isinstance(attempt, Mapping)]
    numeric = [int(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    return sum(numeric) if numeric else None


def _stage_latency(stage: Mapping[str, Any] | None) -> float:
    direct = _stage_number(stage, "elapsed_seconds")
    if isinstance(direct, (int, float)):
        return float(direct)
    if stage is None:
        return 0.0
    attempts = stage.get("attempts")
    if not isinstance(attempts, list):
        return 0.0
    return sum(
        float(attempt["elapsed_seconds"])
        for attempt in attempts
        if isinstance(attempt, Mapping)
        and isinstance(attempt.get("elapsed_seconds"), (int, float))
        and not isinstance(attempt.get("elapsed_seconds"), bool)
    )


def _stage_retry_count(stage: Mapping[str, Any] | None) -> int:
    if stage is None:
        return 0
    value = stage.get("retry_count", 0)
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _parse_failure_stage(record: Mapping[str, Any]) -> str | None:
    for name in ("solver", "critic_independent", "critique", "revision"):
        stage = _stage(record, name)
        if stage is not None and stage.get("status") == "parse_failure":
            value = stage.get("parse_failure_stage")
            return str(value) if isinstance(value, str) else name
    return None


def _record_valid(record: Mapping[str, Any]) -> bool:
    # A valid record must complete all stages required by its verdict.
    if record.get("invalid") is True or record.get("protocol_status") == "invalid":
        return False
    required = ("solver", "critic_independent", "critique")
    if not all(_stage_complete(_stage(record, name)) for name in required):
        return False
    critique = _stage(record, "critique")
    if critique is None:
        return False
    verdict = critique.get("verdict")
    revision = _stage(record, "revision")
    if verdict == "INCORRECT":
        return _stage_complete(revision)
    return verdict == "CORRECT" and revision is None


def _parse_gold_answer(answer_text: str, question_id: str) -> str:
    if "####" not in answer_text:
        raise EvaluationValidationError(f"GSM8K gold answer for {question_id} has no #### marker.")
    return _parse_numeric(answer_text.rsplit("####", 1)[1], context=f"GSM8K gold answer for {question_id}")


def _load_gold_answers(config: Mapping[str, Any], records: Iterable[Mapping[str, Any]]) -> dict[int, GoldAnswer]:
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover - depends on the Kaggle image
        raise RuntimeError("Missing dependency: install datasets before running evaluation.") from exc

    dataset_config = config.get("dataset")
    if not isinstance(dataset_config, Mapping):
        raise EvaluationValidationError("config.yaml has no dataset mapping.")
    name = dataset_config.get("name")
    config_name = dataset_config.get("config_name")
    split_name = dataset_config.get("split", dataset_config.get("generation_split"))
    if not all(isinstance(value, str) and value for value in (name, config_name, split_name)):
        raise EvaluationValidationError("dataset.name, dataset.config_name, and dataset.split are required.")

    dataset = load_dataset(name, config_name, split=split_name)
    records_by_index: dict[int, GoldAnswer] = {}
    requested_indices = {record.get("train_index") for record in records if isinstance(record.get("train_index"), int)}
    if not requested_indices:
        raise EvaluationValidationError("Pipeline records have no train_index values for GSM8K gold lookup.")
    for index in requested_indices:
        if index < 0 or index >= len(dataset):
            raise EvaluationValidationError(f"train_index {index} is outside GSM8K {split_name}.")
        example = dataset[index]
        question = example.get("question")
        answer = example.get("answer")
        if not isinstance(question, str) or not isinstance(answer, str):
            raise EvaluationValidationError(f"GSM8K record {index} has no question/answer text.")
        records_by_index[index] = GoldAnswer(
            answer=_parse_gold_answer(answer, f"gsm8k-{split_name}-{index}"),
            question=question,
            split=split_name,
        )
    return records_by_index


def _direction_counts() -> dict[str, int]:
    return {transition: 0 for transition in TRANSITIONS}


def _transition(solver_correct: bool | None, final_correct: bool | None, valid: bool) -> str | None:
    # Exclude incomplete interactions from transition analysis.
    if not valid or solver_correct is None or final_correct is None:
        return None
    if not solver_correct and final_correct:
        return "HELPED"
    if solver_correct and not final_correct:
        return "HURT"
    if solver_correct and final_correct:
        return "STABLE-CORRECT"
    return "STABLE-WRONG"


def _bool_to_int(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _build_dataset_rows(
    records: list[dict[str, Any]], gold_by_index: Mapping[int, GoldAnswer]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    directions: dict[str, dict[str, int]] = {}
    solver_totals: dict[str, dict[str, int]] = {}
    original_correct = 0
    original_incorrect = 0

    for record in records:
        train_index = record.get("train_index")
        if not isinstance(train_index, int) or train_index not in gold_by_index:
            raise EvaluationValidationError(f"Missing GSM8K gold mapping for {record.get('interaction_id')!r}.")
        gold = gold_by_index[train_index]
        question = record.get("question")
        if question != gold.question:
            raise EvaluationValidationError(
                f"Question text does not match GSM8K at train_index {train_index}; refusing to score mismatched data."
            )
        direction = record.get("direction")
        if not isinstance(direction, str) or not direction:
            raise EvaluationValidationError(f"Record {record.get('interaction_id')!r} has no direction.")

        solver = _stage(record, "solver")
        critic_independent = _stage(record, "critic_independent")
        critique = _stage(record, "critique")
        revision = _stage(record, "revision")

        solver_answer = _stage_answer(solver)
        critic_answer = _stage_answer(critic_independent)
        revision_called = bool(record.get("revision_called", revision is not None))
        revised_answer = _stage_answer(revision) if revision_called else None

        solver_correct = _numeric_equal(solver_answer, gold.answer)
        critic_correct = _numeric_equal(critic_answer, gold.answer)
        revised_correct = _numeric_equal(revised_answer, gold.answer) if revision_called else None
        critic_solver_agree = _numeric_equal(critic_answer, solver_answer)

        critic_verdict = _stage_text(critique, "verdict") if _stage_complete(critique) else None
        critic_error_desc = _stage_text(critique, "error_description") if _stage_complete(critique) else None
        proposed_answer = _stage_text(critique, "proposed_answer") if _stage_complete(critique) else None
        if proposed_answer is not None:
            try:
                proposed_answer = _parse_numeric(proposed_answer, context="critic proposed answer")
            except EvaluationValidationError:
                proposed_answer = None

        if critic_verdict == "CORRECT":
            final_answer = solver_answer
            final_correct = solver_correct
        elif revision_called:
            final_answer = revised_answer
            final_correct = revised_correct
        else:
            final_answer = None
            final_correct = None

        valid = _record_valid(record)
        transition = _transition(solver_correct, final_correct, valid)
        changed_answer = _numeric_equal(solver_answer, final_answer)
        changed_answer = None if changed_answer is None else not changed_answer
        proposed_differs = _numeric_equal(proposed_answer, solver_answer)
        proposed_differs = None if proposed_differs is None else not proposed_differs

        if solver_correct is True:
            original_correct += 1
        elif solver_correct is False:
            original_incorrect += 1
        solver_bucket = solver_totals.setdefault(direction, {"numerator": 0, "denominator": 0, "parse_failures": 0})
        if solver_correct is None:
            solver_bucket["parse_failures"] += 1
        else:
            solver_bucket["denominator"] += 1
            solver_bucket["numerator"] += int(solver_correct)

        if transition is not None:
            directions.setdefault(direction, _direction_counts())[transition] += 1
        else:
            directions.setdefault(direction, _direction_counts())

        stages = (solver, critic_independent, critique, revision)
        row = {
            "question_id": record.get("question_id"),
            "question": question,
            "gold_answer": gold.answer,
            "dataset_split": gold.split,
            "direction": direction,
            "solver_model": record.get("solver_model"),
            "critic_model": record.get("critic_model"),
            "solver_reasoning": _stage_text(solver, "reasoning"),
            "solver_answer": solver_answer,
            "solver_correct": _bool_to_int(solver_correct),
            "critic_independent_reasoning": _stage_text(critic_independent, "reasoning"),
            "critic_independent_answer": critic_answer,
            "critic_independent_correct": _bool_to_int(critic_correct),
            "critic_solver_agree_before_verdict": _bool_to_int(critic_solver_agree),
            "critic_verdict": critic_verdict,
            "critic_error_desc": critic_error_desc,
            "critic_proposed_answer": proposed_answer,
            "revision_called": int(revision_called),
            "revision_reasoning": _stage_text(revision, "reasoning") if revision_called else None,
            "revise_decision": _stage_text(revision, "decision") if revision_called else None,
            "revised_answer": revised_answer,
            "revised_correct": _bool_to_int(revised_correct),
            "changed_answer": _bool_to_int(changed_answer),
            "transition": transition,
            "beneficial": 1 if transition == "HELPED" else (0 if transition is not None else None),
            "valid": int(valid),
            "parse_failure_stage": _parse_failure_stage(record),
            "retry_count": sum(_stage_retry_count(stage) for stage in stages),
            # Downstream stages populate these columns without overwriting raw results.
            "split": None,
            "critic_disagrees": 1 if critic_verdict == "INCORRECT" else (0 if critic_verdict == "CORRECT" else None),
            "proposed_answer_differs": _bool_to_int(proposed_differs),
            "explicit_error_flag": None,
            "hedging_count": None,
            "critique_length": None,
            "self_consistency": None,
            "solver_tokens": _stage_tokens(solver),
            "critic_independent_tokens": _stage_tokens(critic_independent),
            "critique_tokens": _stage_tokens(critique),
            "revision_tokens": _stage_tokens(revision) if revision_called else None,
            "latency_s": round(sum(_stage_latency(stage) for stage in stages), 6),
            "prompt_version": record.get("prompt_version"),
            "timestamp": record.get("saved_at"),
        }
        rows.append(row)

    return rows, {
        "transitions_per_direction": directions,
        "solver_totals_per_direction": solver_totals,
        "original_correct_count": original_correct,
        "original_incorrect_count": original_incorrect,
    }


def _parse_success_per_stage(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int | float | None]]:
    stage_names = {
        "solver_answer": "solver",
        "critic_independent_solve": "critic_independent",
        "critique_verdict": "critique",
        "revision": "revision",
    }
    metrics: dict[str, dict[str, int | float | None]] = {}
    for metric_name, stage_name in stage_names.items():
        attempted = 0
        statuses: list[str] = []
        for record in records:
            stage = _stage(record, stage_name)
            if stage is None:
                continue
            attempted += 1
            statuses.append(str(stage.get("status")))
        success = statuses.count("complete")
        parse_failures = statuses.count("parse_failure")
        generation_failures = statuses.count("generation_error")
        other_failures = attempted - success - parse_failures - generation_failures
        metrics[metric_name] = {
            "attempted_count": attempted,
            "parse_success_count": success,
            "parse_failure_count": parse_failures,
            "generation_failure_count": generation_failures,
            "other_failure_count": other_failures,
            "parse_success_rate": round(success / attempted, 6) if attempted else None,
        }
    return metrics


def _project_helped(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    observed = list(rows)
    evaluated = [row for row in observed if row.get("transition") in TRANSITIONS]
    helped = sum(row.get("transition") == "HELPED" for row in evaluated)
    eligible_count = len(evaluated)
    if eligible_count == 0:
        return {
            "observed_helped_count": 0,
            "observed_transition_eligible_count": 0,
            "observed_interaction_count": len(observed),
            "observed_helped_rate": None,
            "full_scale_interactions_range": list(FULL_SCALE_INTERACTIONS),
            "projected_helped_count_range": None,
            "uncertainty_method": "Not estimable: no transition-eligible pilot interactions.",
            "note": "A 40-50 question pilot is noisy; do not treat any projected count as exact.",
        }
    # Project HELPED cases from the rate across all observed interactions.
    denominator = len(observed)
    rate = helped / denominator
    z = 1.96
    interval_denominator = 1.0 + z**2 / denominator
    center = (rate + z**2 / (2.0 * denominator)) / interval_denominator
    margin = (
        z
        * math.sqrt(rate * (1.0 - rate) / denominator + z**2 / (4.0 * denominator**2))
        / interval_denominator
    )
    lower_rate = max(0.0, center - margin)
    upper_rate = min(1.0, center + margin)
    low_interactions, high_interactions = FULL_SCALE_INTERACTIONS
    return {
        "observed_helped_count": helped,
        "observed_transition_eligible_count": eligible_count,
        "observed_interaction_count": denominator,
        "observed_helped_rate": round(rate, 6),
        "full_scale_interactions_range": [low_interactions, high_interactions],
        "projected_helped_count_range": [
            math.floor(lower_rate * low_interactions),
            math.ceil(upper_rate * high_interactions),
        ],
        "uncertainty_method": "95% Wilson interval applied to the observed pilot HELPED rate.",
        "note": "A 40-50 question pilot is noisy; do not treat any projected count as exact.",
    }


def _validation_warnings(
    records: list[Mapping[str, Any]],
    summary: Mapping[str, Any],
    expected_directions: Iterable[str],
) -> list[str]:
    expected_directions = tuple(expected_directions)
    warnings: list[str] = []
    observed_directions = {str(record.get("direction")) for record in records}
    missing = sorted(set(expected_directions) - observed_directions)
    if missing:
        warnings.append(f"Missing required direction(s): {', '.join(missing)}.")
    unique_questions = int(summary["unique_questions_processed"])
    if not EXPECTED_PILOT_MIN <= unique_questions <= EXPECTED_PILOT_MAX:
        warnings.append(
            f"Pilot has {unique_questions} unique questions; the feasibility checkpoint requires {EXPECTED_PILOT_MIN}-{EXPECTED_PILOT_MAX}."
        )
    expected_interactions = unique_questions * len(expected_directions)
    if int(summary["interactions_processed"]) != expected_interactions:
        warnings.append(
            f"Expected {expected_interactions} saved interactions for both directions; "
            f"found {summary['interactions_processed']}."
        )
    if int(summary["originally_correct_count"]) == 0:
        warnings.append("No originally-correct solver answers were observed.")
    if int(summary["originally_incorrect_count"]) == 0:
        warnings.append("No originally-incorrect solver answers were observed.")
    if int(summary["changed_correctness_count"]) < 5:
        warnings.append("Fewer than 5 changed-correctness interactions were observed across both directions.")
    if int(summary["pooled_transitions"]["HELPED"]) == 0:
        warnings.append("No HELPED cases were observed.")
    return warnings


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DATASET_COLUMNS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")


def load_config(config_path: str | Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on the runtime image
        raise RuntimeError("Missing dependency: install pyyaml before running evaluation.") from exc
    with Path(config_path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise EvaluationValidationError("config.yaml must contain a mapping.")
    return payload


def run_feasibility_evaluation(
    *,
    config_path: str | Path,
    raw_dir: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    """Build dataset.csv and metrics.json from one, prompt-consistent pilot run."""
    config = load_config(config_path)
    raw_path = Path(raw_dir)
    # Evaluate direction-specific interaction records only.
    inputs = sorted(raw_path.glob("interactions_*.jsonl")) if raw_path.is_dir() else [raw_path]
    inputs = [path for path in inputs if path.is_file()]
    if not inputs:
        raise EvaluationValidationError(f"No JSONL input files were found under {raw_path}.")
    records = _read_jsonl(inputs)

    if any(not isinstance(record.get("generation_settings"), Mapping) for record in records):
        raise EvaluationValidationError("Every interaction must carry generation_settings.")
    generation_settings = {json.dumps(record["generation_settings"], sort_keys=True) for record in records}
    if len(generation_settings) != 1:
        raise EvaluationValidationError(
            "Mixed generation_settings cannot be combined in one feasibility metric."
        )
    if any(not isinstance(record.get("prompt_version"), str) or not record["prompt_version"] for record in records):
        raise EvaluationValidationError("Every interaction must carry a prompt_version for checkpoint evaluation.")
    prompt_versions = sorted({str(record.get("prompt_version")) for record in records})
    if len(prompt_versions) != 1:
        raise EvaluationValidationError(
            "Mixed prompt_version values cannot be combined in one feasibility metric: " + ", ".join(prompt_versions)
        )

    # Evaluate only records from one protocol signature and the configured directions.
    if any(not isinstance(record.get("resume_signature"), Mapping) for record in records):
        raise EvaluationValidationError("Every interaction must carry a resume_signature for checkpoint evaluation.")
    resume_signatures = {
        json.dumps(record["resume_signature"], sort_keys=True)
        for record in records
    }
    if len(resume_signatures) != 1:
        raise EvaluationValidationError("Mixed or missing resume_signature values cannot be combined in one feasibility metric.")

    expected_directions = [
        str(direction["name"])
        for direction in config.get("directions", [])
        if isinstance(direction, Mapping) and isinstance(direction.get("name"), str)
    ]
    if len(expected_directions) != 2:
        raise EvaluationValidationError("config.yaml must define exactly two named cross-model directions.")
    observed_directions = {str(record.get("direction")) for record in records}
    unexpected_directions = sorted(observed_directions.difference(expected_directions))
    if unexpected_directions:
        raise EvaluationValidationError(
            "Unexpected direction values cannot be combined in one feasibility metric: "
            + ", ".join(unexpected_directions)
        )

    gold_by_index = _load_gold_answers(config, records)
    rows, aggregates = _build_dataset_rows(records, gold_by_index)
    transitions_per_direction = {
        direction: aggregates["transitions_per_direction"].get(direction, _direction_counts())
        for direction in expected_directions
    }
    pooled_transitions = _direction_counts()
    for counts in transitions_per_direction.values():
        for transition in TRANSITIONS:
            pooled_transitions[transition] += counts[transition]

    solver_per_direction: dict[str, dict[str, int | float]] = {}
    for direction in expected_directions:
        values = aggregates["solver_totals_per_direction"].get(
            direction, {"numerator": 0, "denominator": 0, "parse_failures": 0}
        )
        denominator = values["denominator"]
        solver_per_direction[direction] = {
            **values,
            "rate": round(values["numerator"] / denominator, 6) if denominator else None,
        }
    solver_numerator = sum(value["numerator"] for value in solver_per_direction.values())
    solver_denominator = sum(value["denominator"] for value in solver_per_direction.values())
    solver_parse_failures = sum(value["parse_failures"] for value in solver_per_direction.values())
    parse_success = _parse_success_per_stage(records)
    changed_correctness_count = pooled_transitions["HELPED"] + pooled_transitions["HURT"]

    summary: dict[str, Any] = {
        "unique_questions_processed": len({row["question_id"] for row in rows}),
        "interactions_processed": len(rows),
        "interactions_per_direction": {
            direction: sum(row["direction"] == direction for row in rows) for direction in expected_directions
        },
        "solver_accuracy": {
            "numerator": solver_numerator,
            "denominator": solver_denominator,
            "rate": round(solver_numerator / solver_denominator, 6) if solver_denominator else None,
            "parse_failures": solver_parse_failures,
            "per_direction": solver_per_direction,
        },
        "transitions_per_direction": transitions_per_direction,
        "pooled_transitions": pooled_transitions,
        "changed_correctness_count": changed_correctness_count,
        "parse_success_per_stage": parse_success,
        "projected_helped_range": _project_helped(rows),
        "valid_count": sum(row["valid"] == 1 for row in rows),
        "invalid_count": sum(row["valid"] == 0 for row in rows),
        "prompt_version": prompt_versions[0],
        "prompt_versions": prompt_versions,
        "originally_correct_count": aggregates["original_correct_count"],
        "originally_incorrect_count": aggregates["original_incorrect_count"],
        "feasibility_evidence": {
            "pilot_size_is_40_to_50_questions": EXPECTED_PILOT_MIN
            <= len({row["question_id"] for row in rows})
            <= EXPECTED_PILOT_MAX,
            "both_directions_present": all(
                any(row["direction"] == direction for row in rows) for direction in expected_directions
            ),
            "originally_correct_answers_present": aggregates["original_correct_count"] > 0,
            "originally_incorrect_answers_present": aggregates["original_incorrect_count"] > 0,
            "at_least_5_changed_correctness_interactions": changed_correctness_count >= 5,
            "helped_cases_present": pooled_transitions["HELPED"] > 0,
        },
    }
    blockers = _validation_warnings(records, summary, expected_directions)
    summary["blockers_detected"] = blockers

    root = Path(output_root)
    dataset_path = root / "data" / "processed" / "dataset.csv"
    metrics_path = root / "results" / "metrics.json"
    _write_csv(dataset_path, rows)
    _write_json(metrics_path, summary)
    return {"dataset_path": str(dataset_path), "metrics_path": str(metrics_path), "metrics": summary}


def format_checkpoint_summary(metrics: Mapping[str, Any]) -> str:
    """Return a compact checkpoint summary for notebook output."""
    lines = [
        "Feasibility Checkpoint",
        f"Unique pilot questions: {metrics['unique_questions_processed']}",
        f"Interactions: {metrics['interactions_processed']} ({metrics['interactions_per_direction']})",
    ]
    accuracy = metrics["solver_accuracy"]
    rate = accuracy["rate"]
    percentage = "n/a" if rate is None else f"{rate:.1%}"
    lines.append(
        f"Solver accuracy: {accuracy['numerator']}/{accuracy['denominator']} ({percentage}); "
        f"solver parse failures: {accuracy['parse_failures']}"
    )
    lines.append("Transitions by direction:")
    for direction, counts in metrics["transitions_per_direction"].items():
        lines.append(f"  {direction}: " + ", ".join(f"{name}={counts[name]}" for name in TRANSITIONS))
    lines.append("Pooled: " + ", ".join(f"{name}={metrics['pooled_transitions'][name]}" for name in TRANSITIONS))
    lines.append(f"Changed-correctness interactions: {metrics['changed_correctness_count']}")
    evidence = metrics["feasibility_evidence"]
    lines.append(
        "At least 5 changed-correctness interactions: "
        + ("yes" if evidence["at_least_5_changed_correctness_interactions"] else "no")
    )
    lines.append("HELPED cases present: " + ("yes" if evidence["helped_cases_present"] else "no"))
    lines.append("Parse success by stage:")
    for stage, values in metrics["parse_success_per_stage"].items():
        rate_value = values["parse_success_rate"]
        rate_text = "n/a" if rate_value is None else f"{rate_value:.1%}"
        lines.append(
            f"  {stage}: {values['parse_success_count']}/{values['attempted_count']} ({rate_text}); "
            f"parse_failures={values['parse_failure_count']}; "
            f"generation_failures={values['generation_failure_count']}; "
            f"other_failures={values['other_failure_count']}"
        )
    projection = metrics["projected_helped_range"]
    lines.append(f"Projected HELPED count at 300-500 interactions: {projection['projected_helped_count_range']}")
    lines.append(
        "Scope limitation: the Solver revises only after critic disagreement, so this evaluates selective "
        "revision among disagreement cases only."
    )
    if metrics["blockers_detected"]:
        lines.append("Warnings/blockers: " + " | ".join(metrics["blockers_detected"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the feasibility-checkpoint dataset and metrics.")
    parser.add_argument("--config", default="configs/config.yaml", help="Path to the project config.yaml.")
    parser.add_argument("--raw-dir", default="data/raw", help="Directory containing Pipeline interaction JSONL files.")
    parser.add_argument("--output-root", default=".", help="Writable project root for data/processed and results.")
    args = parser.parse_args(argv)
    result = run_feasibility_evaluation(
        config_path=args.config,
        raw_dir=args.raw_dir,
        output_root=args.output_root,
    )
    print(format_checkpoint_summary(result["metrics"]))
    print(f"dataset.csv: {result['dataset_path']}")
    print(f"metrics.json: {result['metrics_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
