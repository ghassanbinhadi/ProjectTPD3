"""Re-parse failed evaluation revisions without running any model.

The script preserves the supplied raw records, writes a separate corrected
copy, and rebuilds the dataset and transition metrics from that copy.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping
import zipfile


RULE_ID = "v6_final_test_revision_reparse_r1"
DIRECTIONS = (
    "qwen_solver_llama_critic",
    "llama_solver_qwen_critic",
)
TRANSITIONS = ("HELPED", "HURT", "STABLE-CORRECT", "STABLE-WRONG")
FAILED_REVISION_COUNT = 5

CURRENCY = re.compile(r"[$\u20ac\u00a3\u00a5]")
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)")
REASONING_MARKER = re.compile(r"(?m)^[ \t]*REASONING:[ \t]*")
DECISION_LINE = re.compile(r"(?m)^[ \t]*DECISION:[ \t]*(KEEP|CHANGE)[ \t]*$")
FINAL_MARKER = re.compile(r"(?m)^[ \t]*FINAL_ANSWER:[ \t]*")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Malformed JSONL at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise RuntimeError(f"Expected an object at {path}:{line_number}")
            rows.append(value)
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_numeric(fragment: str) -> dict[str, Any]:
    """Apply strict numeric normalization to one extracted answer."""
    raw_extracted = fragment
    value = fragment.strip()
    if not value:
        return {"ok": False, "raw_extracted": raw_extracted, "error": "empty_answer"}
    value = value.strip("*`_")
    if re.search(r"\d\s+[+-]?\d", value):
        return {"ok": False, "raw_extracted": raw_extracted, "error": "multiple_numbers"}
    normalized = re.sub(r"[\s,]+", "", CURRENCY.sub("", value.rstrip(".,;:!?*`_")))
    if not NUMBER.fullmatch(normalized):
        return {
            "ok": False,
            "raw_extracted": raw_extracted,
            "normalized_answer": normalized,
            "error": "not_one_signed_integer_or_decimal",
        }
    return {
        "ok": True,
        "raw_extracted": raw_extracted,
        "normalized_answer": normalized,
        "answer": normalized,
    }


def parse_revision_for_recovery(response: str) -> dict[str, Any]:
    """Allow a preamble, then require one ordered structured block.

    The rule does not inspect the question or gold answer. It requires exactly
    one REASONING marker and one KEEP/CHANGE decision, uses the last
    FINAL_ANSWER marker, and strictly parses the first non-empty answer line.
    """
    reasoning_markers = list(REASONING_MARKER.finditer(response))
    decision_lines = list(DECISION_LINE.finditer(response))
    final_markers = list(FINAL_MARKER.finditer(response))
    if len(reasoning_markers) != 1:
        return {"ok": False, "error": "expected_exactly_one_reasoning_marker"}
    if len(decision_lines) != 1:
        return {"ok": False, "error": "expected_exactly_one_keep_change_decision"}
    if not final_markers:
        return {"ok": False, "error": "missing_final_answer_marker"}

    reasoning_marker = reasoning_markers[0]
    decision_line = decision_lines[0]
    final_marker = final_markers[-1]
    if not (reasoning_marker.end() <= decision_line.start() < final_marker.start()):
        return {"ok": False, "error": "revision_fields_out_of_order"}

    reasoning = response[reasoning_marker.end() : decision_line.start()].strip()
    if not reasoning:
        return {"ok": False, "error": "empty_revision_reasoning"}
    remainder = response[final_marker.end() :]
    answer_line = next((line for line in remainder.splitlines() if line.strip()), "")
    answer = parse_numeric(answer_line)
    if not answer["ok"]:
        return {
            "ok": False,
            "error": f"revision_{answer['error']}",
            "answer_parse": answer,
        }
    return {
        "ok": True,
        "reasoning": reasoning,
        "decision": decision_line.group(1),
        "raw_extracted": answer["raw_extracted"],
        "normalized_answer": answer["normalized_answer"],
        "answer": answer["answer"],
        "preamble_present": bool(response[: reasoning_marker.start()].strip()),
    }


def numeric_equal(left: str, right: str) -> bool:
    return abs(float(left) - float(right)) <= 1e-6


def reparse_record(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    revised = copy.deepcopy(record)
    revision = revised.get("stages", {}).get("revision")
    if not isinstance(revision, dict) or revision.get("status") != "parse_failure":
        return revised, None

    attempts = revision.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise RuntimeError(f"Failed revision has no attempts: {record.get('interaction_id')}")

    candidates: list[dict[str, Any]] = []
    selected_attempt: dict[str, Any] | None = None
    selected_parse: dict[str, Any] | None = None
    for attempt in attempts:
        raw_response = attempt.get("raw_response") if isinstance(attempt, dict) else None
        parsed = (
            parse_revision_for_recovery(raw_response)
            if isinstance(raw_response, str)
            else {"ok": False, "error": "missing_raw_response"}
        )
        candidates.append(
            {
                "attempt": attempt.get("attempt") if isinstance(attempt, dict) else None,
                "generation_settings": attempt.get("generation_settings") if isinstance(attempt, dict) else None,
                "raw_response": raw_response,
                "reparse": parsed,
            }
        )
        if parsed.get("ok") and selected_attempt is None:
            selected_attempt = attempt
            selected_parse = parsed

    audit: dict[str, Any] = {
        "interaction_id": record.get("interaction_id"),
        "question_id": record.get("question_id"),
        "direction": record.get("direction"),
        "rule_id": RULE_ID,
        "gold_used_for_parsing": False,
        "selection_policy": "earliest_attempt_that_satisfies_the_rule",
        "original_status": revision.get("status"),
        "original_error": revision.get("error"),
        "candidate_attempts": candidates,
    }
    if selected_attempt is None or selected_parse is None:
        audit.update({"reparse_status": "still_invalid", "selected_attempt": None})
        return revised, audit

    solver_answer = revised["stages"]["solver"]["answer"]
    answer = selected_parse["answer"]
    decision = selected_parse["decision"]
    answer_changed = not numeric_equal(solver_answer, answer)
    unusual = (decision == "KEEP" and answer_changed) or (decision == "CHANGE" and not answer_changed)

    preserved_retry_count = revision.get("retry_count", 0)
    preserved_attempts = revision["attempts"]
    revision.update(
        {
            "status": "complete",
            "reasoning": selected_parse["reasoning"],
            "decision": decision,
            "answer": answer,
            "normalized_answer": selected_parse["normalized_answer"],
            "raw_extracted": selected_parse["raw_extracted"],
            "raw_response": selected_attempt["raw_response"],
            "prompt": selected_attempt.get("prompt"),
            "prompt_tokens": selected_attempt.get("prompt_tokens"),
            "completion_tokens": selected_attempt.get("completion_tokens"),
            "elapsed_seconds": selected_attempt.get("elapsed_seconds"),
            "model_version": selected_attempt.get("model_version"),
            "answer_changed": answer_changed,
            "decision_answer_pattern": f"{decision}_{'CHANGED' if answer_changed else 'UNCHANGED'}",
            "decision_answer_unusual_flag": unusual,
            "retry_count": preserved_retry_count,
            "attempts": preserved_attempts,
            "posthoc_reparse": {
                "rule_id": RULE_ID,
                "selected_attempt": selected_attempt.get("attempt"),
                "gold_used_for_parsing": False,
            },
        }
    )
    revision.pop("error", None)
    revision.pop("parse_failure_stage", None)
    revised["protocol_status"] = "complete"
    revised["invalid"] = False
    revised["invalid_reason"] = None
    revised["final_answer_after_protocol"] = answer
    revised["posthoc_reparse"] = {
        "rule_id": RULE_ID,
        "stage": "revision",
        "selected_attempt": selected_attempt.get("attempt"),
    }

    audit.update(
        {
            "reparse_status": "recovered",
            "selected_attempt": selected_attempt.get("attempt"),
            "selected_decision": decision,
            "selected_answer": answer,
            "selected_reasoning": selected_parse["reasoning"],
            "preamble_present": selected_parse["preamble_present"],
            "answer_changed": answer_changed,
            "decision_answer_unusual_flag": unusual,
        }
    )
    return revised, audit


def load_gold_answers(arrow_path: Path, records: Iterable[Mapping[str, Any]], verify: Any) -> dict[int, Any]:
    import pyarrow as pa
    import pyarrow.ipc as ipc

    with pa.memory_map(str(arrow_path), "r") as source:
        table = ipc.open_stream(source).read_all()
    if table.num_rows != 1319:
        raise RuntimeError(f"Expected 1319 GSM8K test rows, found {table.num_rows}")
    requested = sorted({record["train_index"] for record in records})
    gold_by_index: dict[int, Any] = {}
    for index in requested:
        example = table.slice(index, 1).to_pylist()[0]
        gold_by_index[index] = verify.GoldAnswer(
            answer=verify._parse_gold_answer(example["answer"], f"gsm8k-test-{index}"),
            question=example["question"],
            split="test",
        )
    return gold_by_index


def transition_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    counts = {direction: {name: 0 for name in TRANSITIONS} for direction in DIRECTIONS}
    for row in rows:
        transition = row.get("transition")
        direction = row.get("direction")
        if direction in counts and transition in TRANSITIONS:
            counts[direction][transition] += 1
    return counts


def summarize(rows: list[dict[str, Any]], records: list[dict[str, Any]], verify: Any) -> dict[str, Any]:
    per_direction = transition_counts(rows)
    pooled = {
        name: sum(per_direction[direction][name] for direction in DIRECTIONS)
        for name in TRANSITIONS
    }
    solver_rows = [row for row in rows if row.get("solver_correct") in (0, 1)]
    return {
        "unique_questions": len({row["question_id"] for row in rows}),
        "interactions": len(rows),
        "interactions_per_direction": {
            direction: sum(row["direction"] == direction for row in rows)
            for direction in DIRECTIONS
        },
        "valid_count": sum(row["valid"] == 1 for row in rows),
        "invalid_count": sum(row["valid"] == 0 for row in rows),
        "solver_accuracy": {
            "numerator": sum(row["solver_correct"] == 1 for row in solver_rows),
            "denominator": len(solver_rows),
            "rate": round(sum(row["solver_correct"] == 1 for row in solver_rows) / len(solver_rows), 6),
            "parse_failures": len(rows) - len(solver_rows),
        },
        "transitions_per_direction": per_direction,
        "pooled_transitions": pooled,
        "changed_correctness_count": pooled["HELPED"] + pooled["HURT"],
        "parse_success_per_stage": verify._parse_success_per_stage(records),
    }


def row_key(row: Mapping[str, Any]) -> str:
    return f"{row['direction']}::{row['question_id']}"


def stage_snapshot(stage: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(stage, Mapping):
        return None
    return {
        key: stage.get(key)
        for key in (
            "status",
            "model_id",
            "reasoning",
            "answer",
            "verdict",
            "error_description",
            "proposed_answer",
            "decision",
            "raw_response",
            "retry_count",
        )
        if key in stage
    }


def build_demo(record: Mapping[str, Any], row: Mapping[str, Any], kind: str) -> dict[str, Any]:
    stages = record["stages"]
    return {
        "demo_type": kind,
        "interaction_id": record["interaction_id"],
        "question_id": row["question_id"],
        "direction": row["direction"],
        "question": row["question"],
        "gold_answer": row["gold_answer"],
        "solver_answer": row["solver_answer"],
        "solver_correct": bool(row["solver_correct"]),
        "critic_verdict": row["critic_verdict"],
        "critic_proposed_answer": row["critic_proposed_answer"],
        "revised_answer": row["revised_answer"],
        "revised_correct": bool(row["revised_correct"]),
        "transition": row["transition"],
        "why_selected": (
            "The Solver was wrong, the Critic correctly disagreed, and revision changed the answer to the gold value."
            if kind == "clean_helped"
            else "The Solver was correct, the Critic incorrectly disagreed, and revision changed the answer away from the gold value."
        ),
        "stages": {
            "solver": stage_snapshot(stages.get("solver")),
            "critic_independent": stage_snapshot(stages.get("critic_independent")),
            "critique": stage_snapshot(stages.get("critique")),
            "revision": stage_snapshot(stages.get("revision")),
        },
    }


def write_audit_csv(path: Path, audits: list[dict[str, Any]]) -> None:
    fields = (
        "interaction_id",
        "question_id",
        "direction",
        "original_status",
        "original_error",
        "reparse_status",
        "selected_attempt",
        "selected_decision",
        "selected_answer",
        "preamble_present",
        "gold_used_for_parsing",
        "before_transition",
        "after_transition",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: audit.get(field) for field in fields} for audit in audits)


def write_summary_markdown(path: Path, summary: Mapping[str, Any]) -> None:
    before = summary["before"]
    after = summary["after"]
    lines = [
        "# V6 Final Test Revision Re-parse",
        "",
        "No model generation was run. The original archive and V6 code were not modified.",
        "",
        "## Deterministic rule",
        "",
        summary["reparse_rule"],
        "",
        "The attempts are checked in original order and the earliest parseable attempt is selected. Gold answers are not available to the parser.",
        "",
        "## Before and after",
        "",
        "| Metric | Before | After |",
        "|---|---:|---:|",
        f"| Valid | {before['valid_count']} | {after['valid_count']} |",
        f"| Invalid | {before['invalid_count']} | {after['invalid_count']} |",
        f"| HELPED | {before['pooled_transitions']['HELPED']} | {after['pooled_transitions']['HELPED']} |",
        f"| HURT | {before['pooled_transitions']['HURT']} | {after['pooled_transitions']['HURT']} |",
        f"| STABLE-CORRECT | {before['pooled_transitions']['STABLE-CORRECT']} | {after['pooled_transitions']['STABLE-CORRECT']} |",
        f"| STABLE-WRONG | {before['pooled_transitions']['STABLE-WRONG']} | {after['pooled_transitions']['STABLE-WRONG']} |",
        "",
        "## After re-parsing by direction",
        "",
        "| Direction | HELPED | HURT | STABLE-CORRECT | STABLE-WRONG |",
        "|---|---:|---:|---:|---:|",
    ]
    for direction in DIRECTIONS:
        counts = after["transitions_per_direction"][direction]
        lines.append(
            f"| {direction} | {counts['HELPED']} | {counts['HURT']} | "
            f"{counts['STABLE-CORRECT']} | {counts['STABLE-WRONG']} |"
        )
    lines.extend(
        [
            "",
            f"Recovered revisions: {summary['reparse']['recovered_count']}/{summary['reparse']['attempted_count']}.",
            f"Remaining invalid interactions: {after['invalid_count']} (both are non-revision failures).",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_demo_markdown(path: Path, demos: list[Mapping[str, Any]]) -> None:
    lines = ["# Final Test Demo Candidates", ""]
    for demo in demos:
        lines.extend(
            [
                f"## {demo['demo_type']}",
                "",
                f"- Interaction: `{demo['interaction_id']}`",
                f"- Direction: `{demo['direction']}`",
                f"- Solver answer: `{demo['solver_answer']}`",
                f"- Critic verdict: `{demo['critic_verdict']}`",
                f"- Critic proposed answer: `{demo['critic_proposed_answer']}`",
                f"- Revised answer: `{demo['revised_answer']}`",
                f"- Gold answer: `{demo['gold_answer']}`",
                f"- Transition: `{demo['transition']}`",
                f"- Why: {demo['why_selected']}",
                "",
                f"**Question:** {demo['question']}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_archive(output_root: Path) -> Path:
    archive = output_root.parent / f"{output_root.name}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output_root.parent))
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--gsm8k-test-arrow", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.project_root.resolve()))
    from src import verify

    raw_files = sorted((args.source_root / "data" / "raw").glob("interactions_*.jsonl"))
    if len(raw_files) != 2:
        raise RuntimeError(f"Expected two direction JSONL files, found {len(raw_files)}")
    original_by_file = {path.name: read_jsonl(path) for path in raw_files}
    original_records = [row for rows in original_by_file.values() for row in rows]
    if len(original_records) != 300:
        raise RuntimeError(f"Expected 300 interactions, found {len(original_records)}")
    if len({row["interaction_id"] for row in original_records}) != 300:
        raise RuntimeError("Original interactions contain duplicate IDs")

    corrected_by_file: dict[str, list[dict[str, Any]]] = {}
    audits: list[dict[str, Any]] = []
    for filename, rows in original_by_file.items():
        corrected_rows: list[dict[str, Any]] = []
        for row in rows:
            corrected, audit = reparse_record(row)
            corrected_rows.append(corrected)
            if audit is not None:
                audits.append(audit)
        corrected_by_file[filename] = corrected_rows

    if len(audits) != FAILED_REVISION_COUNT:
        raise RuntimeError(f"Expected {FAILED_REVISION_COUNT} revision failures, found {len(audits)}")

    corrected_records = [row for rows in corrected_by_file.values() for row in rows]
    gold = load_gold_answers(args.gsm8k_test_arrow, original_records, verify)
    before_rows, _ = verify._build_dataset_rows(original_records, gold)
    after_rows, _ = verify._build_dataset_rows(corrected_records, gold)
    before = summarize(before_rows, original_records, verify)
    after = summarize(after_rows, corrected_records, verify)

    before_by_key = {row_key(row): row for row in before_rows}
    after_by_key = {row_key(row): row for row in after_rows}
    for audit in audits:
        key = f"{audit['direction']}::{audit['question_id']}"
        audit["before_transition"] = before_by_key[key]["transition"]
        audit["after_transition"] = after_by_key[key]["transition"]
        audit["gold_answer"] = after_by_key[key]["gold_answer"]
        audit["solver_answer"] = after_by_key[key]["solver_answer"]
        audit["solver_correct"] = after_by_key[key]["solver_correct"]
        audit["revised_correct"] = after_by_key[key]["revised_correct"]

    unchanged_ids = set(row["interaction_id"] for row in original_records) - {
        audit["interaction_id"] for audit in audits
    }
    original_map = {row["interaction_id"]: row for row in original_records}
    corrected_map = {row["interaction_id"]: row for row in corrected_records}
    if any(original_map[key] != corrected_map[key] for key in unchanged_ids):
        raise RuntimeError("A non-target interaction was modified")

    output_root = args.output_root.resolve()
    for filename, rows in corrected_by_file.items():
        write_jsonl(output_root / "data" / "reparsed" / filename, rows)
    verify._write_csv(output_root / "data" / "processed" / "dataset_reparsed.csv", after_rows)
    write_jsonl(output_root / "audit" / "revision_reparse_audit.jsonl", audits)
    write_audit_csv(output_root / "audit" / "revision_reparse_audit.csv", audits)

    record_by_id = {row["interaction_id"]: row for row in corrected_records}
    row_by_key = {row_key(row): row for row in after_rows}
    preferred_helped = "llama_solver_qwen_critic::gsm8k-test-922"
    preferred_hurt = "qwen_solver_llama_critic::gsm8k-test-252"
    helped_row = row_by_key[preferred_helped]
    hurt_row = row_by_key[preferred_hurt]
    if helped_row["transition"] != "HELPED":
        raise RuntimeError("Preferred HELPED demo is not HELPED after re-parsing")
    if not (
        hurt_row["transition"] == "HURT"
        and hurt_row["solver_correct"] == 1
        and hurt_row["critic_verdict"] == "INCORRECT"
    ):
        raise RuntimeError("Preferred false-alarm HURT demo does not satisfy its definition")
    demos = [
        build_demo(record_by_id[preferred_helped], helped_row, "clean_helped"),
        build_demo(record_by_id[preferred_hurt], hurt_row, "false_alarm_hurt"),
    ]
    write_json(output_root / "demos" / "demo_cases.json", demos)
    write_demo_markdown(output_root / "demos" / "demo_cases.md", demos)

    summary = {
        "source_archive": str(args.source_archive.resolve()),
        "source_archive_sha256": sha256(args.source_archive),
        "rule_id": RULE_ID,
        "reparse_rule": (
            "Allow arbitrary preamble before one exact REASONING marker; require exactly one DECISION line "
            "containing KEEP or CHANGE; use the last FINAL_ANSWER marker and strictly parse the first "
            "non-empty line after it as one signed integer or decimal. Process attempts in original order "
            "and select the earliest parseable attempt."
        ),
        "gold_used_for_parsing": False,
        "before": before,
        "after": after,
        "reparse": {
            "attempted_count": len(audits),
            "recovered_count": sum(audit["reparse_status"] == "recovered" for audit in audits),
            "still_invalid_count": sum(audit["reparse_status"] == "still_invalid" for audit in audits),
            "selected_attempts": {
                str(attempt): sum(audit.get("selected_attempt") == attempt for audit in audits)
                for attempt in (1, 2)
            },
        },
        "demo_interaction_ids": [demo["interaction_id"] for demo in demos],
    }
    write_json(output_root / "results" / "before_after_summary.json", summary)
    write_json(output_root / "results" / "metrics_reparsed.json", after)
    write_summary_markdown(output_root / "results" / "before_after_summary.md", summary)

    checksums = {
        str(path.relative_to(output_root)): sha256(path)
        for path in sorted(output_root.rglob("*"))
        if path.is_file()
    }
    write_json(output_root / "checksums.json", checksums)
    archive = build_archive(output_root)

    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"Output root: {output_root}")
    print(f"Archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
