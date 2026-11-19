from __future__ import annotations
import random


# -----------------------------
# RANGE CONFIG (SYNC WITH ML)
# -----------------------------
MODEL_RANGES = {
    "0-9": (0, 9),
    "10-19": (10, 19),
    "20-29": (20, 29),
    "30-39": (30, 39),
    "40-50": (40, 50),
}

DIFFICULTY_LEVELS = {"easy", "standard", "hard"}


def generate_question(operation: str, difficulty_level: str = "standard") -> dict:
    if difficulty_level not in DIFFICULTY_LEVELS:
        raise ValueError("Unsupported difficulty level")

    if operation == "addition":
        minimum, maximum = {
            "easy": (0, 10),
            "standard": (0, 25),
            "hard": (10, 25),
        }[difficulty_level]
        left = random.randint(minimum, maximum)
        right = random.randint(minimum, maximum)
        answer = left + right
        operator = "+"

    elif operation == "subtraction":
        minimum_left, maximum_left, minimum_right = {
            "easy": (0, 20, 0),
            "standard": (10, 50, 0),
            "hard": (25, 50, 10),
        }[difficulty_level]
        left = random.randint(minimum_left, maximum_left)
        right = random.randint(minimum_right, left)
        answer = left - right
        operator = "-"

    elif operation == "multiplication":
        if difficulty_level == "easy":
            left = random.randint(0, 5)
            max_right = 5 if left == 0 else min(5, 25 // left)
            right = random.randint(0, max_right)
        elif difficulty_level == "standard":
            left = random.randint(0, 10)
            max_right = 10 if left == 0 else min(10, 50 // left)
            right = random.randint(0, max_right)
        else:
            left = random.randint(5, 10)
            max_right = min(10, 50 // left)
            right = random.randint(5, max_right)
        answer = left * right
        operator = "x"

    elif operation == "division":
        if difficulty_level == "easy":
            right = random.randint(1, 5)
            answer = random.randint(0, 5)
        elif difficulty_level == "standard":
            right = random.randint(1, 10)
            answer = random.randint(0, 10)
        else:
            right = random.randint(6, 10)
            answer = random.randint(1, 50 // right)
        left = answer * right
        operator = "/"

    else:
        raise ValueError("Unsupported operation")

    return {
        "operation": operation,
        "left": left,
        "right": right,
        "operator": operator,
        "answer": answer,
    }


def validate_answer(operation: str, left: int, right: int, predicted_number: int) -> dict:

    if operation == "addition":
        expected = left + right
        operator = "+"

    elif operation == "subtraction":
        expected = left - right
        operator = "-"

    elif operation == "multiplication":
        expected = left * right
        operator = "x"

    elif operation == "division":
        expected = left // right
        operator = "/"

    else:
        raise ValueError("Unsupported operation")

    return {
        "left": left,
        "right": right,
        "operator": operator,
        "expected_answer": expected,
        "predicted_answer": predicted_number,
        "is_correct": int(predicted_number) == int(expected),
    }


# -----------------------------
# NEW: MODEL SELECTION HELPER
# -----------------------------
def get_model_key_for_number(number: int) -> str:
    for key, (low, high) in MODEL_RANGES.items():
        if low <= number <= high:
            return key
    return "10-19"  # fallback