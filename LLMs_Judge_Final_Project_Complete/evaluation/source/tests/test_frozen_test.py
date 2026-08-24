from __future__ import annotations

import copy
import csv
from pathlib import Path
import tempfile
import unittest

from src.interact import (
    EventLog,
    Pipeline,
    build_artifact_paths,
    frozen_selection_report,
    load_config,
    load_or_select_questions,
    resume_signature,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "config_final_test.yaml"


def fake_dataset() -> dict[str, list[dict[str, str]]]:
    return {
        "train": [{"question": f"train question {index}", "answer": "#### 0"} for index in range(7473)],
        "test": [{"question": f"test question {index}", "answer": "#### 0"} for index in range(1319)],
    }


def write_ids(path: Path, identifiers: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["question_id"])
        writer.writerows([identifier] for identifier in identifiers)


class FrozenTestSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(CONFIG_PATH)
        self.dataset = fake_dataset()

    def test_official_file_matches_exactly_150_test_questions(self) -> None:
        report, questions = frozen_selection_report(self.dataset, self.config)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["number_of_frozen_ids"], 150)
        self.assertEqual(report["number_of_unique_ids"], 150)
        self.assertEqual(report["matched_gsm8k_questions"], 150)
        self.assertEqual(report["expected_interactions"], 300)
        self.assertEqual(report["missing_ids"], [])
        self.assertEqual(report["duplicate_ids"], [])
        self.assertEqual(questions[0]["question_id"], report["first_5_ids"][0])
        self.assertEqual(questions[-1]["question_id"], report["last_5_ids"][-1])

    def test_duplicate_and_train_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ids.csv"
            identifiers = [f"gsm8k-test-{index}" for index in range(148)]
            identifiers.extend(["gsm8k-test-0", "gsm8k-train-1"])
            write_ids(path, identifiers)
            config = copy.deepcopy(self.config)
            config["dataset"]["frozen_question_ids_file"] = str(path)
            report, _ = frozen_selection_report(self.dataset, config)
            self.assertIn("gsm8k-test-0", report["duplicate_ids"])
            self.assertIn("gsm8k-train-1", report["wrong_split_ids"])
            self.assertTrue(report["errors"])

    def test_saved_selection_is_reused_without_resampling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = build_artifact_paths(root, self.config)
            logger = EventLog(root / "test_events.jsonl")
            first = load_or_select_questions(self.dataset, self.config, paths, logger)
            second = load_or_select_questions(self.dataset, self.config, paths, logger)
            self.assertEqual(first, second)
            self.assertEqual(len(first), 150)
            self.assertEqual(len({row["question_id"] for row in first}), 150)

    def test_resume_signature_changes_when_frozen_ids_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ids.csv"
            identifiers = [f"gsm8k-test-{index}" for index in range(150)]
            write_ids(path, identifiers)
            config = copy.deepcopy(self.config)
            config["dataset"]["frozen_question_ids_file"] = str(path)
            first = resume_signature(config)
            identifiers[-1] = "gsm8k-test-200"
            write_ids(path, identifiers)
            second = resume_signature(config)
            self.assertNotEqual(
                first["dataset"]["frozen_question_ids_sha256"],
                second["dataset"]["frozen_question_ids_sha256"],
            )

    def test_resume_skips_a_saved_question_direction_pair(self) -> None:
        report, questions = frozen_selection_report(self.dataset, self.config)
        self.assertEqual(report["errors"], [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = build_artifact_paths(root, self.config)
            logger = EventLog(root / "test_events.jsonl")
            first = Pipeline(self.config, paths, questions, logger)
            self.assertEqual(len(first.states), 300)
            self.assertEqual(len(set(first.states)), 300)
            interaction_id = next(iter(first.states))
            state = first.states[interaction_id]
            state["stages"] = {
                "solver": {"stage": "solver", "status": "complete", "answer": "1", "model_version": "test"},
                "critic_independent": {
                    "stage": "critic_independent", "status": "complete", "answer": "1", "model_version": "test",
                },
                "critique": {
                    "stage": "critique", "status": "complete", "verdict": "CORRECT", "model_version": "test",
                },
            }
            first.finish_terminal_states()
            self.assertIn(interaction_id, first.completed_ids)

            resumed = Pipeline(self.config, paths, questions, logger)
            self.assertIn(interaction_id, resumed.completed_ids)
            self.assertNotIn(interaction_id, {row["interaction_id"] for row in resumed.states_for(state["direction"])})


if __name__ == "__main__":
    unittest.main()
