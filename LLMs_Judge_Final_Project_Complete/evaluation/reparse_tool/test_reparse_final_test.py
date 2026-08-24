import unittest

from reparse_final_test import parse_revision_for_recovery, reparse_record


class RevisionRecoveryParserTests(unittest.TestCase):
    def test_accepts_preamble_and_inline_numeric_answer(self):
        parsed = parse_revision_for_recovery(
            "Preamble with calculations.\nREASONING: critique is valid\n"
            "DECISION: CHANGE\nFINAL_ANSWER: 42"
        )
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["decision"], "CHANGE")
        self.assertEqual(parsed["answer"], "42")

    def test_accepts_blank_lines_before_numeric_answer(self):
        parsed = parse_revision_for_recovery(
            "REASONING: original remains correct\nDECISION: KEEP\nFINAL_ANSWER:\n\n  42."
        )
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["answer"], "42")

    def test_rejects_units(self):
        parsed = parse_revision_for_recovery(
            "REASONING: revised\nDECISION: CHANGE\nFINAL_ANSWER: 42 kg"
        )
        self.assertFalse(parsed["ok"])

    def test_rejects_old_decision_vocabulary(self):
        parsed = parse_revision_for_recovery(
            "REASONING: revised\nDECISION: ACCEPT\nFINAL_ANSWER: 42"
        )
        self.assertFalse(parsed["ok"])

    def test_rejects_ambiguous_multiple_decisions(self):
        parsed = parse_revision_for_recovery(
            "REASONING: revised\nDECISION: KEEP\nDECISION: CHANGE\nFINAL_ANSWER: 42"
        )
        self.assertFalse(parsed["ok"])

    def test_selects_earliest_parseable_attempt_without_gold(self):
        record = {
            "interaction_id": "direction::question",
            "question_id": "question",
            "direction": "direction",
            "protocol_status": "invalid",
            "invalid": True,
            "invalid_reason": "revision_parse_failure",
            "final_answer_after_protocol": None,
            "stages": {
                "solver": {"answer": "10"},
                "revision": {
                    "stage": "revision",
                    "status": "parse_failure",
                    "error": "revision_format_invalid",
                    "parse_failure_stage": "revision",
                    "retry_count": 1,
                    "attempts": [
                        {
                            "attempt": 1,
                            "raw_response": "Preamble\nREASONING: first\nDECISION: KEEP\nFINAL_ANSWER: 10",
                        },
                        {
                            "attempt": 2,
                            "raw_response": "Preamble\nREASONING: second\nDECISION: CHANGE\nFINAL_ANSWER: 20",
                        },
                    ],
                },
            },
        }
        corrected, audit = reparse_record(record)
        self.assertEqual(audit["selected_attempt"], 1)
        self.assertEqual(corrected["stages"]["revision"]["answer"], "10")
        self.assertFalse(audit["gold_used_for_parsing"])


if __name__ == "__main__":
    unittest.main()
