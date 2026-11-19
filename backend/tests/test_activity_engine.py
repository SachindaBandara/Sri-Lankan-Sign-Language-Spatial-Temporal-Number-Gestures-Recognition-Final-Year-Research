import unittest
from unittest.mock import patch

from utils.activity_engine import generate_question


class ActivityEngineTests(unittest.TestCase):
    def test_all_difficulty_levels_apply_operation_specific_ranges(self):
        cases = (
            ("addition", "easy", (0, 0), 0),
            ("addition", "standard", (0, 0), 0),
            ("addition", "hard", (10, 10), 20),
            ("subtraction", "easy", (0, 0), 0),
            ("subtraction", "standard", (10, 0), 10),
            ("subtraction", "hard", (25, 10), 15),
            ("multiplication", "easy", (0, 0), 0),
            ("multiplication", "standard", (0, 0), 0),
            ("multiplication", "hard", (5, 5), 25),
            ("division", "easy", (0, 1), 0),
            ("division", "standard", (0, 1), 0),
            ("division", "hard", (6, 6), 1),
        )

        for operation, difficulty, operands, expected_answer in cases:
            with self.subTest(operation=operation, difficulty=difficulty):
                with patch("utils.activity_engine.random.randint", side_effect=lambda low, high: low):
                    question = generate_question(operation, difficulty)
                self.assertEqual((question["left"], question["right"]), operands)
                self.assertEqual(question["answer"], expected_answer)
                self.assertLessEqual(question["answer"], 50)

    def test_standard_remains_the_default_difficulty(self):
        with patch("utils.activity_engine.random.randint", side_effect=lambda low, high: high) as randint:
            question = generate_question("addition")

        self.assertEqual((question["left"], question["right"]), (25, 25))
        self.assertEqual(question["answer"], 50)
        self.assertEqual(randint.call_args_list[0].args, (0, 25))

    def test_unknown_difficulty_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_question("addition", "expert")
