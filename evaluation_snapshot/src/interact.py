"""Resumable Solver-Critic Pipeline for the LLMs_Judge Pipeline lane."""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys
import time
import traceback
from typing import Any, Callable, Iterable, Iterator
import uuid
import zipfile

import yaml

from configs.prompts import PROMPT_VERSION, render_prompt
from src.models import FourBitModel, GenerationOutput


FINAL_ANSWER = "FINAL_ANSWER:"
CURRENCY = re.compile(r"[$\u20ac\u00a3\u00a5]")
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)")
QUESTION_ID = re.compile(r"gsm8k-(train|test)-(\d+)")
Parser = Callable[[str], dict[str, Any]]


class DatasetValidationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return ()
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Malformed JSONL at {path}:{line_number}") from exc
    return rows


class EventLog:
    def __init__(self, path: Path):
        self.path = path

    def write(self, event: str, **details: Any) -> None:
        row = {"timestamp": utc_now(), "event": event, **details}
        append_jsonl(self.path, row)
        identity = details.get("interaction_id") or details.get("model_id") or ""
        print(f"[{row['timestamp']}] {event} {identity}".rstrip())


@dataclass(frozen=True)
class ArtifactPaths:
    root: Path
    raw_dir: Path
    selected_questions: Path
    checkpoint: Path
    metadata: Path
    execution_log: Path
    pipeline_outputs: Path
    archive: Path


def build_artifact_paths(root: Path, config: dict[str, Any]) -> ArtifactPaths:
    paths = config["paths"]
    return ArtifactPaths(
        root, root / paths["raw_dir"], root / paths["selected_questions_file"],
        root / paths["checkpoint_file"], root / paths["metadata_file"],
        root / paths["execution_log_file"], root / paths["pipeline_outputs_file"],
        root / paths["archive_file"],
    )


def load_config(path: str | Path, *, strict: bool = True) -> dict[str, Any]:
    with Path(path).resolve().open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    required = {"project", "dataset", "models", "directions", "quantization", "decoding", "runtime", "paths"}
    if not isinstance(config, dict):
        raise ValueError("config.yaml must contain a mapping.")
    missing = sorted(required.difference(config))
    if missing:
        raise ValueError(f"config.yaml is missing required sections: {', '.join(missing)}")
    if not config["project"].get("schema_version"):
        raise ValueError("project.schema_version is required.")
    # Validate fixed decoding settings before the run starts.
    if config["decoding"].get("do_sample") is not False:
        raise ValueError("The specification requires decoding.do_sample=false.")
    if int(config["decoding"].get("max_new_tokens", 0)) <= 0:
        raise ValueError("decoding.max_new_tokens must be a positive integer.")
    retry_decoding = config["decoding"].get("retry")
    if not isinstance(retry_decoding, dict) or retry_decoding.get("do_sample") is not True:
        raise ValueError("V6 retry decoding requires decoding.retry.do_sample=true.")
    if float(retry_decoding.get("temperature", 0)) <= 0:
        raise ValueError("decoding.retry.temperature must be positive.")
    if int(config["runtime"].get("parse_retry_count", -1)) != 1:
        raise ValueError("V6 protocol requires exactly one parse retry.")
    sample_size = int(config["dataset"].get("sample_size", 0))
    pilot_size = int(config["dataset"].get("pilot_size", sample_size))
    if sample_size <= 0 or pilot_size <= 0 or pilot_size > sample_size:
        raise ValueError("dataset.sample_size must be positive and dataset.pilot_size must be within the selected cohort.")
    if strict and not 40 <= pilot_size <= 50:
        raise ValueError("The official pilot needs dataset.pilot_size between 40 and 50.")
    directions = config["directions"]
    if not isinstance(directions, list) or len(directions) != 2:
        raise ValueError("The specification requires both cross-model directions.")
    for direction in directions:
        solver, critic = direction.get("solver_model"), direction.get("critic_model")
        if not direction.get("name") or solver == critic or solver not in config["models"] or critic not in config["models"]:
            raise ValueError("Each direction needs two distinct configured models and a name.")
    return config


def parse_numeric(fragment: str, raw_extracted: str | None = None) -> dict[str, Any]:
    """Normalize permitted formatting and accept exactly one numeric value."""
    audit_value, value = raw_extracted if raw_extracted is not None else fragment, fragment.strip()
    if not value:
        return {"ok": False, "raw_extracted": audit_value, "error": "empty_answer"}
    value = value.strip("*`_")
    if re.search(r"\d\s+[+-]?\d", value):
        return {"ok": False, "raw_extracted": audit_value, "error": "multiple_numbers"}
    normalized = re.sub(r"[\s,]+", "", CURRENCY.sub("", value.rstrip(".,;:!?*`_")))
    if not NUMBER.fullmatch(normalized):
        return {"ok": False, "raw_extracted": audit_value, "normalized_answer": normalized, "error": "not_one_signed_integer_or_decimal"}
    return {"ok": True, "raw_extracted": audit_value, "normalized_answer": normalized, "answer": normalized}


def parse_final_answer(response: str) -> dict[str, Any]:
    # Validate only the first non-empty line after the final marker.
    if FINAL_ANSWER not in response:
        return {"ok": False, "raw_extracted": None, "error": "missing_final_answer_marker"}
    reasoning, raw = response.rsplit(FINAL_ANSWER, 1)
    answer_line = next((line for line in raw.splitlines() if line.strip()), "")
    parsed = parse_numeric(answer_line, answer_line)
    if parsed["ok"]:
        parsed["reasoning"] = reasoning.strip()
    return parsed


def parse_critique(response: str) -> dict[str, Any]:
    match = re.fullmatch(
        r"VERDICT:\s*(CORRECT|INCORRECT)\s*\nERROR_DESCRIPTION:\s*(.*?)\s*\nPROPOSED_ANSWER:\s*(.+?)\s*",
        response.strip(), flags=re.DOTALL,
    )
    if match is None:
        return {"ok": False, "error": "critique_format_invalid"}
    verdict, error_description, proposed_raw = match.groups()
    error_description = error_description.strip()
    if verdict == "CORRECT" and error_description.lower() != "none":
        return {"ok": False, "error": "correct_verdict_requires_none_error_description"}
    if verdict == "INCORRECT" and (not error_description or error_description.lower() == "none"):
        return {"ok": False, "error": "incorrect_verdict_requires_error_description"}
    proposed = parse_numeric(proposed_raw, proposed_raw)
    if not proposed["ok"]:
        return {"ok": False, "error": f"proposed_answer_{proposed['error']}", "proposed_parse": proposed}
    return {
        "ok": True, "verdict": verdict, "error_description": error_description,
        "proposed_answer": proposed["answer"], "proposed_raw": proposed["raw_extracted"],
        "proposed_normalized": proposed["normalized_answer"],
    }


def parse_revision(response: str) -> dict[str, Any]:
    # Accept an inline or next-line answer and validate only its first non-empty line.
    match = re.fullmatch(
        r"REASONING:\s*(.*?)\s*\nDECISION:\s*(KEEP|CHANGE)\s*\nFINAL_ANSWER:(.*)",
        response.strip(), flags=re.DOTALL,
    )
    if match is None:
        return {"ok": False, "error": "revision_format_invalid"}
    reasoning, decision, remainder = match.groups()
    answer_line = next((line for line in remainder.splitlines() if line.strip()), "")
    if not answer_line:
        return {"ok": False, "error": "revision_empty_answer"}
    answer = parse_numeric(answer_line, answer_line)
    if not answer["ok"]:
        return {"ok": False, "error": f"revision_{answer['error']}", "answer_parse": answer}
    return {
        "ok": True, "reasoning": reasoning.strip(), "decision": decision,
        "raw_extracted": answer["raw_extracted"], "normalized_answer": answer["normalized_answer"], "answer": answer["answer"],
    }


def validate_gsm8k(config: dict[str, Any], logger: EventLog | None) -> Any:
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover - Kaggle dependency
        raise RuntimeError("Install datasets before running the Pipeline.") from exc
    source = config["dataset"]
    if logger is not None:
        logger.write("dataset_validation_started", dataset=source["name"], config=source["config_name"])
    dataset = load_dataset(source["name"], source["config_name"])
    if {"train", "test"}.difference(dataset):
        raise DatasetValidationError("GSM8K must provide train and test splits.")
    if len(dataset["train"]) != int(source["expected_train_size"]) or len(dataset["test"]) != int(source["expected_test_size"]):
        raise DatasetValidationError("Unexpected GSM8K split size.")
    if any(not {"question", "answer"}.issubset(dataset[split].column_names) for split in ("train", "test")):
        raise DatasetValidationError("GSM8K must contain question and answer columns.")
    if logger is not None:
        logger.write("dataset_validation_completed", train_size=len(dataset["train"]), test_size=len(dataset["test"]))
    return dataset


def question_hash(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def resolve_frozen_question_ids_file(config: dict[str, Any]) -> Path | None:
    value = config["dataset"].get("frozen_question_ids_file")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError("dataset.frozen_question_ids_file must be a non-empty path.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    path = path.resolve()
    if not path.is_file():
        raise DatasetValidationError(f"Frozen question ID file does not exist: {path}")
    return path


def read_frozen_question_ids(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["question_id"]:
            raise DatasetValidationError("Frozen CSV must contain exactly one column named question_id.")
        identifiers = [str(row.get("question_id", "")).strip() for row in reader]
    if any(not identifier for identifier in identifiers):
        raise DatasetValidationError("Frozen CSV contains an empty question_id.")
    return identifiers


def frozen_selection_report(dataset: Any, config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    settings = config["dataset"]
    split_name = str(settings.get("generation_split", ""))
    frozen_path = resolve_frozen_question_ids_file(config)
    if frozen_path is None:
        raise DatasetValidationError("dataset.frozen_question_ids_file is required for frozen-test validation.")

    identifiers = read_frozen_question_ids(frozen_path)
    seen: set[str] = set()
    duplicate_ids: list[str] = []
    for identifier in identifiers:
        if identifier in seen and identifier not in duplicate_ids:
            duplicate_ids.append(identifier)
        seen.add(identifier)

    invalid_format_ids: list[str] = []
    wrong_split_ids: list[str] = []
    missing_ids: list[str] = []
    questions: list[dict[str, Any]] = []
    split = dataset[split_name] if split_name in dataset else None
    for identifier in identifiers:
        match = QUESTION_ID.fullmatch(identifier)
        if match is None:
            invalid_format_ids.append(identifier)
            missing_ids.append(identifier)
            continue
        identifier_split, index_text = match.groups()
        if identifier_split != "test" or split_name != "test":
            wrong_split_ids.append(identifier)
            missing_ids.append(identifier)
            continue
        index = int(index_text)
        if split is None or not 0 <= index < len(split):
            missing_ids.append(identifier)
            continue
        questions.append({
            "question_id": identifier,
            # Retain this field name for compatibility with saved interactions.
            "train_index": index,
            "question": split[index]["question"],
        })

    errors: list[str] = []
    if split_name != "test":
        errors.append("dataset.generation_split must be test for the final held-out run")
    if int(settings.get("sample_size", 0)) != 150:
        errors.append("dataset.sample_size must be 150 for the frozen final test")
    if len(identifiers) != 150:
        errors.append(f"frozen CSV must contain exactly 150 IDs; found {len(identifiers)}")
    if duplicate_ids:
        errors.append("frozen CSV contains duplicate IDs")
    if invalid_format_ids:
        errors.append("frozen CSV contains malformed IDs")
    if wrong_split_ids:
        errors.append("frozen CSV contains IDs outside gsm8k-test-*")
    if missing_ids:
        errors.append("one or more frozen IDs do not match GSM8K test")

    report = {
        "prompt_version": PROMPT_VERSION,
        "dataset_split": split_name,
        "frozen_csv_path": str(frozen_path),
        "frozen_csv_sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
        "number_of_frozen_ids": len(identifiers),
        "number_of_unique_ids": len(set(identifiers)),
        "first_5_ids": identifiers[:5],
        "last_5_ids": identifiers[-5:],
        "matched_gsm8k_questions": len(questions),
        "missing_ids": missing_ids,
        "duplicate_ids": duplicate_ids,
        "invalid_format_ids": invalid_format_ids,
        "wrong_split_ids": wrong_split_ids,
        "expected_interactions": len(identifiers) * len(config["directions"]),
        "directions": [direction["name"] for direction in config["directions"]],
        "errors": errors,
    }
    return report, questions


def validate_frozen_test_setup(config_path: str | Path) -> dict[str, Any]:
    config_file = Path(config_path).resolve()
    config = load_config(config_file, strict=True)
    if config["project"].get("schema_version") != "V6" or PROMPT_VERSION != "V6":
        raise DatasetValidationError("Final-test validation requires the V6 schema and V6 prompts.")
    dataset = validate_gsm8k(config, logger=None)
    report, _ = frozen_selection_report(dataset, config)
    for key in (
        "prompt_version", "dataset_split", "frozen_csv_path", "number_of_frozen_ids",
        "number_of_unique_ids", "first_5_ids", "last_5_ids", "matched_gsm8k_questions",
        "missing_ids", "duplicate_ids", "expected_interactions", "directions",
    ):
        print(f"{key}: {json.dumps(report[key], ensure_ascii=True)}")
    if report["errors"]:
        raise DatasetValidationError("Frozen test validation failed: " + "; ".join(report["errors"]))
    return report


def resume_signature(config: dict[str, Any]) -> dict[str, Any]:
    """Return the protocol settings that must remain fixed across a resumed run."""
    project_root = Path(__file__).resolve().parents[1]
    source_hashes = {
        relative: hashlib.sha256((project_root / relative).read_bytes()).hexdigest()
        for relative in ("configs/prompts.py", "src/models.py", "src/interact.py")
    }
    dataset_signature = {
        key: config["dataset"][key]
        for key in ("name", "config_name", "generation_split", "sample_size", "pilot_size", "random_seed")
    }
    frozen_path = resolve_frozen_question_ids_file(config)
    if frozen_path is not None:
        dataset_signature.update(
            selection_mode="frozen_question_ids",
            frozen_question_ids_sha256=hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
        )
    return {
        "schema_version": config["project"]["schema_version"],
        "prompt_version": PROMPT_VERSION,
        "source_hashes": source_hashes,
        "dataset": dataset_signature,
        "models": config["models"],
        "directions": config["directions"],
        "quantization": config["quantization"],
        "decoding": config["decoding"],
        "runtime": {
            key: config["runtime"][key]
            for key in ("device_map", "use_chat_template", "parse_retry_count")
        },
    }


def load_or_select_questions(dataset: Any, config: dict[str, Any], paths: ArtifactPaths, logger: EventLog) -> list[dict[str, Any]]:
    settings = config["dataset"]
    frozen_path = resolve_frozen_question_ids_file(config)
    if frozen_path is not None:
        report, questions = frozen_selection_report(dataset, config)
        if report["errors"]:
            raise DatasetValidationError("Frozen test validation failed: " + "; ".join(report["errors"]))
        if paths.selected_questions.exists():
            saved = read_json(paths.selected_questions)
            items = saved.get("selected_question_ids") if isinstance(saved, dict) else None
            if not isinstance(items, list):
                raise RuntimeError("selected_questions.json is invalid; refusing to continue.")
            source = saved.get("dataset", {})
            expected_source = (settings["name"], settings["config_name"], "test")
            if (source.get("name"), source.get("config_name"), source.get("split")) != expected_source:
                raise RuntimeError("selected_questions.json refers to another dataset or split.")
            if saved.get("selection_mode") != "frozen_question_ids":
                raise RuntimeError("selected_questions.json was not created from frozen question IDs.")
            if saved.get("frozen_question_ids_sha256") != report["frozen_csv_sha256"]:
                raise RuntimeError("Frozen question ID file changed; use a new output_root.")
            saved_ids = [item.get("question_id") for item in items if isinstance(item, dict)]
            expected_ids = [question["question_id"] for question in questions]
            if saved_ids != expected_ids:
                raise RuntimeError("selected_questions.json does not match the frozen CSV order and IDs.")
            for item, question in zip(items, questions):
                if item.get("train_index") != question["train_index"]:
                    raise RuntimeError("selected_questions.json contains a mismatched GSM8K test index.")
                if item.get("question_sha256") != question_hash(question["question"]):
                    raise RuntimeError("Persisted question hash no longer matches GSM8K test.")
            logger.write("selection_reused", selected_questions_file=str(paths.selected_questions), count=len(questions), selection_mode="frozen_question_ids")
            return questions

        write_json_atomic(paths.selected_questions, {
            "schema_version": config["project"]["schema_version"], "created_at": utc_now(),
            "dataset": {"name": settings["name"], "config_name": settings["config_name"], "split": "test"},
            "sample_size": len(questions), "selection_mode": "frozen_question_ids",
            "frozen_question_ids_file": frozen_path.name,
            "frozen_question_ids_sha256": report["frozen_csv_sha256"],
            "selected_question_ids": [
                {"question_id": row["question_id"], "train_index": row["train_index"], "question_sha256": question_hash(row["question"])}
                for row in questions
            ],
        })
        logger.write("selection_created", selected_questions_file=str(paths.selected_questions), count=len(questions), selection_mode="frozen_question_ids")
        return questions

    train = dataset["train"]
    if paths.selected_questions.exists():
        saved = read_json(paths.selected_questions)
        items = saved.get("selected_question_ids") if isinstance(saved, dict) else None
        if not isinstance(items, list):
            raise RuntimeError("selected_questions.json is invalid; refusing to resample.")
        if int(saved.get("sample_size", -1)) != int(settings["sample_size"]):
            raise RuntimeError("selected_questions.json sample_size does not match config; use a new output_root.")
        if int(saved.get("random_seed", -1)) != int(settings["random_seed"]):
            raise RuntimeError("selected_questions.json random_seed does not match config; use a new output_root.")
        source = saved.get("dataset", {})
        if (source.get("name"), source.get("config_name"), source.get("split")) != (settings["name"], settings["config_name"], "train"):
            raise RuntimeError("selected_questions.json refers to another dataset; refusing to resample.")
        questions, seen = [], set()
        for item in items:
            index = item.get("train_index")
            if not isinstance(index, int) or index in seen or not 0 <= index < len(train):
                raise RuntimeError("selected_questions.json contains invalid or duplicate train indices.")
            question = train[index]["question"]
            if item.get("question_sha256") != question_hash(question):
                raise RuntimeError("Persisted question hash no longer matches GSM8K.")
            seen.add(index)
            questions.append({"question_id": item["question_id"], "train_index": index, "question": question})
        logger.write("selection_reused", selected_questions_file=str(paths.selected_questions), count=len(questions))
        return questions

    indices = random.Random(int(settings["random_seed"])).sample(range(len(train)), int(settings["sample_size"]))
    questions = [{"question_id": f"gsm8k-train-{index}", "train_index": index, "question": train[index]["question"]} for index in indices]
    write_json_atomic(paths.selected_questions, {
        "schema_version": config["project"]["schema_version"], "created_at": utc_now(),
        "dataset": {"name": settings["name"], "config_name": settings["config_name"], "split": "train"},
        "sample_size": settings["sample_size"], "random_seed": settings["random_seed"],
        "selected_question_ids": [
            {"question_id": row["question_id"], "train_index": row["train_index"], "question_sha256": question_hash(row["question"])}
            for row in questions
        ],
    })
    logger.write("selection_created", selected_questions_file=str(paths.selected_questions), count=len(questions), seed=settings["random_seed"])
    return questions


def generate_and_parse(
    model: FourBitModel, stage: str, prompt: str, parser: Parser, decoding: dict[str, Any],
    parse_retry_count: int, logger: EventLog, interaction_id: str,
) -> dict[str, Any]:
    """Run a stage and retry one parse failure with the unchanged prompt."""
    attempts: list[dict[str, Any]] = []
    # Keep the prompt fixed; use sampled decoding only for the single retry.
    for attempt in range(1, parse_retry_count + 2):
        attempt_decoding = {key: value for key, value in decoding.items() if key != "retry"}
        attempt_prompt = prompt
        if attempt > 1:
            attempt_decoding.update(decoding["retry"])
        logger.write(
            "prompt_execution_started", interaction_id=interaction_id, stage=stage, attempt=attempt,
            model_id=model.model_id, generation_settings=attempt_decoding,
            prompt_variant="base",
        )
        try:
            output: GenerationOutput = model.generate(attempt_prompt, attempt_decoding)
        except Exception as exc:
            details = traceback.format_exc()
            logger.write("generation_error", interaction_id=interaction_id, stage=stage, attempt=attempt, error_type=type(exc).__name__, error=str(exc), traceback=details)
            return {
                "stage": stage, "status": "generation_error", "prompt": prompt, "attempts": attempts,
                "generation_failure_stage": stage, "retry_count": attempt - 1, "error": "generation_error",
                "error_type": type(exc).__name__, "error_message": str(exc), "traceback": details,
            }
        parsed = parser(output.text)
        entry = {
            "attempt": attempt, "prompt": attempt_prompt, "raw_response": output.text, "model_version": output.model_version,
            "prompt_tokens": output.prompt_tokens, "completion_tokens": output.completion_tokens,
            "elapsed_seconds": output.elapsed_seconds, "generation_settings": attempt_decoding, "parse": parsed,
        }
        attempts.append(entry)
        logger.write("stage_parsed", interaction_id=interaction_id, stage=stage, attempt=attempt, parse_ok=parsed["ok"], elapsed_seconds=output.elapsed_seconds)
        if parsed["ok"]:
            return {
                "stage": stage, "status": "complete", "prompt": prompt, "raw_response": output.text,
                "model_id": model.model_id, "model_version": output.model_version, "prompt_tokens": output.prompt_tokens,
                "completion_tokens": output.completion_tokens, "elapsed_seconds": output.elapsed_seconds,
                "retry_count": attempt - 1, "attempts": attempts,
                **{key: value for key, value in parsed.items() if key != "ok"},
            }
        if attempt <= parse_retry_count:
            logger.write("parse_retry", interaction_id=interaction_id, stage=stage, retry_number=attempt)
    last = attempts[-1]
    return {
        "stage": stage, "status": "parse_failure", "prompt": prompt, "raw_response": last["raw_response"],
        "model_id": model.model_id, "model_version": last["model_version"], "prompt_tokens": last["prompt_tokens"],
        "completion_tokens": last["completion_tokens"], "elapsed_seconds": last["elapsed_seconds"], "attempts": attempts,
        "parse_failure_stage": stage, "retry_count": parse_retry_count, "error": last["parse"]["error"],
    }


class Pipeline:
    def __init__(self, config: dict[str, Any], paths: ArtifactPaths, questions: list[dict[str, Any]], logger: EventLog):
        self.config, self.paths, self.questions, self.logger = config, paths, questions, logger
        self.signature = resume_signature(config)
        saved = read_json(paths.checkpoint)
        self.resuming = isinstance(saved, dict)
        self.checkpoint = saved if self.resuming else self._new_checkpoint()
        if self.resuming and self.checkpoint.get("prompt_version") != PROMPT_VERSION:
            raise RuntimeError("Checkpoint prompt_version differs from the current prompts; use a new output_root.")
        if self.resuming and self.checkpoint.get("resume_signature") != self.signature:
            raise RuntimeError("Checkpoint protocol settings differ from config.yaml; use a new output_root.")
        self.checkpoint.setdefault("states", {})
        self.checkpoint.setdefault("completed_ids", [])
        self.states: dict[str, dict[str, Any]] = self.checkpoint["states"]
        self.completed_ids = set(self.checkpoint["completed_ids"])
        self.date = str(self.checkpoint.setdefault("run_date", run_date()))
        self.raw_files = {direction["name"]: self._raw_file(direction) for direction in config["directions"]}
        self._recover_completed_ids()
        self._initialize_states()
        self.save_checkpoint("checkpoint_initialized")
        if self.resuming:
            logger.write("resume_detected", run_id=self.checkpoint["run_id"], completed=len(self.completed_ids))

    def _new_checkpoint(self) -> dict[str, Any]:
        return {
            "schema_version": self.config["project"]["schema_version"],
            "prompt_version": PROMPT_VERSION,
            "resume_signature": self.signature,
            "run_id": str(uuid.uuid4()),
            "created_at": utc_now(),
            "run_date": run_date(),
            "states": {},
            "completed_ids": [],
        }

    def model_id(self, key: str) -> str:
        try:
            return str(self.config["models"][key]["id"])
        except KeyError as exc:
            raise ValueError(f"Unknown model key in direction configuration: {key}") from exc

    def _raw_file(self, direction: dict[str, Any]) -> Path:
        return self.paths.raw_dir / f"interactions_{slug(self.model_id(direction['solver_model']))}_{slug(self.model_id(direction['critic_model']))}_{self.date}.jsonl"

    def _recover_completed_ids(self) -> None:
        output_rows = list(read_jsonl(self.paths.pipeline_outputs))
        output_ids: set[str] = set()
        for row in output_rows:
            self._validate_saved_record(row, self.paths.pipeline_outputs)
            identifier = row["interaction_id"]
            if identifier in output_ids:
                raise RuntimeError(f"Duplicate interaction_id in {self.paths.pipeline_outputs}: {identifier}")
            output_ids.add(identifier)

        raw_ids: set[str] = set()
        repaired = 0
        for raw_file in self.raw_files.values():
            for row in read_jsonl(raw_file):
                self._validate_saved_record(row, raw_file)
                identifier = row["interaction_id"]
                if identifier in raw_ids:
                    raise RuntimeError(f"Duplicate interaction_id in raw JSONL: {identifier}")
                raw_ids.add(identifier)
                if identifier not in output_ids:
                    append_jsonl(self.paths.pipeline_outputs, row)
                    output_ids.add(identifier)
                    repaired += 1
        if output_ids.difference(raw_ids):
            raise RuntimeError("pipeline_outputs.jsonl contains interactions missing from direction raw JSONL.")
        if self.completed_ids.difference(raw_ids):
            raise RuntimeError("Checkpoint marks interactions complete that are missing from raw JSONL.")
        recovered = len(raw_ids.difference(self.completed_ids))
        self.completed_ids.update(raw_ids)
        if repaired:
            self.logger.write("pipeline_outputs_repaired", count=repaired)
        if recovered:
            self.logger.write("completed_interactions_recovered", count=recovered)

    def _validate_saved_record(self, row: dict[str, Any], source: Path) -> None:
        identifier = row.get("interaction_id")
        if not isinstance(identifier, str) or not identifier:
            raise RuntimeError(f"Saved interaction in {source} has no interaction_id.")
        if row.get("resume_signature") != self.signature:
            raise RuntimeError(f"Saved interaction settings differ from the current run in {source}.")

    def _initialize_states(self) -> None:
        for direction in self.config["directions"]:
            for question in self.questions:
                identifier = f"{direction['name']}::{question['question_id']}"
                if identifier not in self.completed_ids:
                    self.states.setdefault(identifier, {
                        "interaction_id": identifier, "direction": direction["name"], "question_id": question["question_id"],
                        "train_index": question["train_index"], "question": question["question"],
                        "solver_model": self.model_id(direction["solver_model"]), "critic_model": self.model_id(direction["critic_model"]),
                        "created_at": utc_now(), "stages": {}, "invalid": False, "invalid_reason": None,
                    })

    def save_checkpoint(self, event: str) -> None:
        self.checkpoint.update(states=self.states, completed_ids=sorted(self.completed_ids), updated_at=utc_now())
        write_json_atomic(self.paths.checkpoint, self.checkpoint)
        self.logger.write(event, checkpoint_file=str(self.paths.checkpoint), completed=len(self.completed_ids))

    def states_for(self, direction: str) -> list[dict[str, Any]]:
        return [state for state in self.states.values() if state["direction"] == direction and state["interaction_id"] not in self.completed_ids]

    @staticmethod
    def stage_complete(state: dict[str, Any], stage: str) -> bool:
        return state["stages"].get(stage, {}).get("status") == "complete"

    @staticmethod
    def terminal(state: dict[str, Any]) -> bool:
        critique = state["stages"].get("critique", {})
        return state["invalid"] or (critique.get("status") == "complete" and critique.get("verdict") == "CORRECT") or state["stages"].get("revision", {}).get("status") == "complete"

    def store_stage(self, state: dict[str, Any], stage: str, result: dict[str, Any]) -> None:
        state["stages"][stage] = result
        if result["status"] != "complete":
            state["invalid"], state["invalid_reason"] = True, stage
            self.logger.write("warning", interaction_id=state["interaction_id"], stage=stage, status=result["status"], error=result.get("error"))

    def finish_terminal_states(self) -> None:
        saved = False
        for state in self.states.values():
            identifier = state["interaction_id"]
            if identifier in self.completed_ids or not self.terminal(state):
                continue
            record = self.materialize(state)
            append_jsonl(self.raw_files[state["direction"]], record)
            append_jsonl(self.paths.pipeline_outputs, record)
            self.completed_ids.add(identifier)
            saved = True
            self.logger.write("interaction_saved", interaction_id=identifier, raw_file=str(self.raw_files[state["direction"]]), invalid=state["invalid"])
        if saved:
            self.save_checkpoint("checkpoint_after_interaction_save")

    def materialize(self, state: dict[str, Any]) -> dict[str, Any]:
        stages = state["stages"]
        solver, revision = stages.get("solver", {}), stages.get("revision", {})
        return {
            "schema_version": self.config["project"]["schema_version"], "record_type": "pipeline_interaction", "saved_at": utc_now(),
            "interaction_id": state["interaction_id"], "direction": state["direction"], "question_id": state["question_id"],
            "train_index": state["train_index"], "question": state["question"], "solver_model": state["solver_model"], "critic_model": state["critic_model"],
            "model_versions": {name: stage["model_version"] for name, stage in stages.items() if stage.get("model_version")},
            "prompt_version": PROMPT_VERSION, "generation_settings": self.config["decoding"], "quantization": self.config["quantization"],
            "resume_signature": self.signature,
            "stages": stages, "revision_called": "revision" in stages,
            "final_answer_after_protocol": revision.get("answer") if revision.get("status") == "complete" else solver.get("answer"),
            "protocol_status": "invalid" if state["invalid"] else "complete", "invalid": state["invalid"], "invalid_reason": state["invalid_reason"],
        }

    def run(self) -> None:
        for direction in self.config["directions"]:
            self.logger.write("direction_started", direction=direction["name"], solver_model=self.model_id(direction["solver_model"]), critic_model=self.model_id(direction["critic_model"]))
            self._run_stage(direction, "solver_model", "solver", lambda state: not state["invalid"] and "solver" not in state["stages"])
            self._run_critic(direction)
            self._run_stage(direction, "solver_model", "revision", lambda state: not state["invalid"] and self.stage_complete(state, "critique") and state["stages"]["critique"]["verdict"] == "INCORRECT" and "revision" not in state["stages"])
            self.finish_terminal_states()
            self.save_checkpoint("direction_checkpoint")
            self.logger.write("direction_completed", direction=direction["name"])

    @contextmanager
    def model_session(self, model_id: str, stage: str) -> Iterator[FourBitModel]:
        self.logger.write("model_loading", model_id=model_id, stage=stage)
        model = FourBitModel(model_id, self.config["quantization"], self.config["runtime"])
        try:
            model.load()
            self.logger.write("model_loaded", model_id=model_id, stage=stage)
            yield model
        finally:
            model.unload()
            self.logger.write("model_unloaded", model_id=model_id, stage=stage)

    def _run_stage(self, direction: dict[str, Any], model_key: str, stage: str, ready: Callable[[dict[str, Any]], bool]) -> None:
        states = [state for state in self.states_for(direction["name"]) if ready(state)]
        if states:
            with self.model_session(self.model_id(direction[model_key]), stage) as model:
                for state in states:
                    self.execute_stage(model, stage, state)

    def _run_critic(self, direction: dict[str, Any]) -> None:
        pending = self.states_for(direction["name"])
        needs_critic = any(not state["invalid"] and ((self.stage_complete(state, "solver") and "critic_independent" not in state["stages"]) or (self.stage_complete(state, "critic_independent") and "critique" not in state["stages"])) for state in pending)
        if not needs_critic:
            return
        with self.model_session(self.model_id(direction["critic_model"]), "critic_independent_and_critique") as model:
            for state in self.states_for(direction["name"]):
                if not state["invalid"] and self.stage_complete(state, "solver") and "critic_independent" not in state["stages"]:
                    self.execute_stage(model, "critic_independent", state)
            for state in self.states_for(direction["name"]):
                if not state["invalid"] and self.stage_complete(state, "critic_independent") and "critique" not in state["stages"]:
                    self.execute_stage(model, "critique", state)

    def execute_stage(self, model: FourBitModel, stage: str, state: dict[str, Any]) -> None:
        identifier = state["interaction_id"]
        try:
            prompt, parser = self.prompt_and_parser(stage, state)
            result = generate_and_parse(model, stage, prompt, parser, self.config["decoding"], int(self.config["runtime"]["parse_retry_count"]), self.logger, identifier)
            if stage == "revision" and result.get("status") == "complete":
                self.annotate_revision_consistency(state, result)
        except Exception as exc:
            details = traceback.format_exc()
            self.logger.write("stage_unexpected_error", interaction_id=identifier, stage=stage, error_type=type(exc).__name__, error=str(exc), traceback=details)
            result = {"stage": stage, "status": "stage_error", "retry_count": 0, "error": f"unexpected_{type(exc).__name__}", "error_type": type(exc).__name__, "error_message": str(exc), "traceback": details}
        self.store_stage(state, stage, result)
        self.save_checkpoint("checkpoint_after_stage")
        self.finish_terminal_states()

    @staticmethod
    def numeric_equal(left: Any, right: Any) -> bool:
        try:
            return abs(float(left) - float(right)) <= 1e-6
        except (TypeError, ValueError):
            return False

    def annotate_revision_consistency(self, state: dict[str, Any], result: dict[str, Any]) -> None:
        changed = not self.numeric_equal(state["stages"]["solver"].get("answer"), result.get("answer"))
        decision = result["decision"]
        result["answer_changed"] = changed
        result["decision_answer_pattern"] = f"{decision}_{'CHANGED' if changed else 'UNCHANGED'}"
        result["decision_answer_unusual_flag"] = (decision == "KEEP" and changed) or (decision == "CHANGE" and not changed)

    def prompt_and_parser(self, stage: str, state: dict[str, Any]) -> tuple[str, Parser]:
        question = state["question"]
        if stage in {"solver", "critic_independent"}:
            return render_prompt(stage, question=question), parse_final_answer
        if stage == "critique":
            solver, critic = state["stages"]["solver"], state["stages"]["critic_independent"]
            return render_prompt("critique", question=question, critic_reasoning=critic["reasoning"], critic_answer=critic["answer"], solver_answer=solver["answer"]), parse_critique
        if stage == "revision":
            solver, critique = state["stages"]["solver"], state["stages"]["critique"]
            return render_prompt("revision", question=question, solver_answer=solver["answer"], error_description=critique["error_description"], proposed_answer=critique["proposed_answer"]), parse_revision
        raise ValueError(f"Unsupported Pipeline stage: {stage}")

    def is_complete(self) -> bool:
        return len(self.completed_ids) == len(self.questions) * len(self.config["directions"])


def write_metadata(config: dict[str, Any], paths: ArtifactPaths, pipeline: Pipeline, status: str, started_at: str) -> None:
    dataset = config["dataset"]
    dataset_metadata = {
        key: dataset[key]
        for key in ("name", "config_name", "source_url", "generation_split", "expected_train_size", "expected_test_size")
    }
    frozen_path = resolve_frozen_question_ids_file(config)
    if frozen_path is not None:
        dataset_metadata.update(
            selection_mode="frozen_question_ids",
            frozen_question_ids_file=frozen_path.name,
            frozen_question_ids_sha256=hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
        )
    directions = [{
        "name": direction["name"], "solver_model": pipeline.model_id(direction["solver_model"]), "critic_model": pipeline.model_id(direction["critic_model"]),
        "interaction_file": str(pipeline.raw_files[direction["name"]].relative_to(paths.root)),
    } for direction in config["directions"]]
    write_json_atomic(paths.metadata, {
        "schema_version": config["project"]["schema_version"], "prompt_version": PROMPT_VERSION,
        "resume_signature": pipeline.signature,
        "run_id": pipeline.checkpoint["run_id"], "run_date": pipeline.date, "status": status,
        "started_at": started_at, "updated_at": utc_now(),
        "dataset": dataset_metadata,
        "sample_size": len(pipeline.questions), "selected_cohort_size": dataset["sample_size"],
        "random_seed": dataset["random_seed"],
        "selected_questions_file": str(paths.selected_questions.relative_to(paths.root)), "quantization": config["quantization"],
        "decoding": config["decoding"], "directions": directions, "completed_interactions": len(pipeline.completed_ids),
    })


def create_archive(paths: ArtifactPaths) -> None:
    files = [paths.selected_questions, paths.checkpoint, paths.metadata, paths.execution_log, paths.pipeline_outputs, *sorted(paths.raw_dir.glob("*.jsonl"))]
    with zipfile.ZipFile(paths.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.exists() and path != paths.archive:
                archive.write(path, path.relative_to(paths.root))


def resolve_runtime_root(config: dict[str, Any], source_root: Path, output_root: str | Path | None) -> Path:
    if output_root is not None:
        root = Path(output_root)
    elif os.environ.get("PIPELINE_OUTPUT_ROOT"):
        root = Path(os.environ["PIPELINE_OUTPUT_ROOT"])
    else:
        working = Path(config["paths"]["kaggle_working_dir"])
        root = Path(config["paths"]["kaggle_project_dir"]) if working.exists() or os.environ.get("KAGGLE_KERNEL_RUN_TYPE") else source_root
    input_root = Path(config["paths"]["kaggle_working_dir"]).parent / "input"
    if input_root.exists() and is_within(root, input_root):
        raise RuntimeError("Kaggle input is read-only. Generated artifacts must be under /kaggle/working/.")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _run_pipeline_from_config(
    config: dict[str, Any], config_file: Path, output_root: str | Path | None, question_limit: int | None,
) -> dict[str, Any]:
    root = resolve_runtime_root(config, config_file.parent.parent, output_root)
    paths = build_artifact_paths(root, config)
    paths.raw_dir.mkdir(parents=True, exist_ok=True)
    logger, started_at, started_clock = EventLog(paths.execution_log), utc_now(), time.perf_counter()
    logger.write("pipeline_started", config_file=str(config_file), output_root=str(root))
    dataset = validate_gsm8k(config, logger)
    # Reuse one saved cohort; run its configured prefix for the pilot.
    cohort = load_or_select_questions(dataset, config, paths, logger)
    limit = int(config["dataset"]["pilot_size"]) if question_limit is None else int(question_limit)
    if not 1 <= limit <= len(cohort):
        raise ValueError(f"question_limit must be between 1 and the selected cohort size ({len(cohort)}).")
    questions = cohort[:limit]
    pipeline = Pipeline(config, paths, questions, logger)
    write_metadata(config, paths, pipeline, "running", started_at)
    try:
        pipeline.run()
    except Exception as exc:
        logger.write("pipeline_error", error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
        write_metadata(config, paths, pipeline, "interrupted", started_at)
        create_archive(paths)
        raise
    status = "complete" if pipeline.is_complete() else "incomplete"
    write_metadata(config, paths, pipeline, status, started_at)
    logger.write("pipeline_completed", status=status, completed=len(pipeline.completed_ids), elapsed_seconds=time.perf_counter() - started_clock)
    create_archive(paths)
    return {"status": status, "completed_interactions": len(pipeline.completed_ids), "output_root": str(paths.root), "raw_directory": str(paths.raw_dir), "checkpoint": str(paths.checkpoint), "metadata": str(paths.metadata), "archive": str(paths.archive)}


def run_pipeline(
    config_path: str | Path | None = None, output_root: str | Path | None = None, question_limit: int | None = None,
) -> dict[str, Any]:
    config_file = Path(config_path or Path(__file__).resolve().parents[1] / "configs" / "config.yaml").resolve()
    return _run_pipeline_from_config(load_config(config_file, strict=True), config_file, output_root, question_limit)


def run_debug_pipeline(config_path: str | Path | None = None, output_root: str | Path | None = None, sample_size: int = 5, max_new_tokens: int | None = None) -> dict[str, Any]:
    config_file = Path(config_path or Path(__file__).resolve().parents[1] / "configs" / "config.yaml").resolve()
    config = copy.deepcopy(load_config(config_file, strict=False))
    if not 1 <= int(sample_size) <= 10:
        raise ValueError("Debug sample_size must be between 1 and 10.")
    # Keep debug artifacts separate from the saved pilot cohort.
    if output_root is None:
        working_dir = Path(config["paths"]["kaggle_working_dir"])
        base_dir = working_dir if working_dir.exists() or os.environ.get("KAGGLE_KERNEL_RUN_TYPE") else config_file.parent.parent / "debug_artifacts"
        output_root = base_dir / f"debug_{int(sample_size)}_{PROMPT_VERSION.lower()}"
    config["dataset"]["sample_size"] = int(sample_size)
    config["dataset"]["pilot_size"] = int(sample_size)
    if max_new_tokens is not None:
        if int(max_new_tokens) <= 0:
            raise ValueError("max_new_tokens must be a positive integer.")
        config["decoding"]["max_new_tokens"] = int(max_new_tokens)
    return _run_pipeline_from_config(config, config_file, output_root, question_limit=None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the GSM8K Solver-Critic Pipeline.")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "configs" / "config.yaml"))
    parser.add_argument("--output-root", help="Writable artifact directory; never use /kaggle/input/.")
    parser.add_argument("--question-limit", type=int, help="Run the first N questions from the saved cohort.")
    parser.add_argument("--debug-sample-size", type=int, help="Run a 1-10 question debug sample.")
    parser.add_argument("--debug-max-new-tokens", type=int, help="Override max_new_tokens for a debug run only.")
    parser.add_argument("--validate-frozen-test", action="store_true", help="Validate frozen GSM8K test IDs without loading LLMs.")
    args = parser.parse_args(argv)
    if args.validate_frozen_test:
        validate_frozen_test_setup(args.config)
        return 0
    result = run_pipeline(args.config, args.output_root, args.question_limit) if args.debug_sample_size is None else run_debug_pipeline(args.config, args.output_root, args.debug_sample_size, args.debug_max_new_tokens)
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
