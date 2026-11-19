"""Enforce learning-record value and summary invariants.

Revision ID: 0005_learning_data_checks
Revises: 0004_preserve_learning_history
"""
from alembic import op


revision = "0005_learning_data_checks"
down_revision = "0004_preserve_learning_history"
branch_labels = None
depends_on = None


CHECK_CONSTRAINTS = {
    "users": (
        ("ck_users_role", "`role` IN ('student', 'teacher')"),
        ("ck_users_active_boolean", "`is_active` IN (0, 1)"),
        ("ck_users_grade", "`grade` IS NULL OR `grade` BETWEEN 1 AND 13"),
    ),
    "student_learning_sessions": (
        (
            "ck_learning_sessions_status",
            "`status` IN ('in_progress', 'completed', 'abandoned')",
        ),
        (
            "ck_learning_sessions_duration",
            "`total_duration_ms` IS NULL OR `total_duration_ms` >= 0",
        ),
    ),
    "student_activity_attempts": (
        (
            "ck_activity_operation",
            "`operation_type` IN "
            "('number_identification', 'addition', 'subtraction', 'multiplication', 'division')",
        ),
        (
            "ck_activity_difficulty",
            "`difficulty_level` IN ('easy', 'standard', 'hard')",
        ),
        (
            "ck_activity_number_difficulty",
            "`operation_type` <> 'number_identification' OR `difficulty_level` = 'standard'",
        ),
        (
            "ck_activity_status",
            "`status` IN ('in_progress', 'completed', 'abandoned')",
        ),
        (
            "ck_activity_nonnegative_counts",
            "`total_questions` >= 0 AND `total_attempts` >= 0 "
            "AND `completed_questions` >= 0 AND `skipped_questions` >= 0 "
            "AND `correct_answers` >= 0 AND `incorrect_answers` >= 0",
        ),
        (
            "ck_activity_attempt_summary",
            "`total_attempts` = `correct_answers` + `incorrect_answers`",
        ),
        (
            "ck_activity_question_summary",
            "`completed_questions` <= `correct_answers` "
            "AND `completed_questions` + `skipped_questions` <= `total_questions`",
        ),
    ),
    "learning_questions": (
        (
            "ck_question_nonnegative_operands",
            "`left_operand` >= 0 AND `right_operand` >= 0",
        ),
        ("ck_question_answer_range", "`expected_answer` BETWEEN 0 AND 50"),
        ("ck_question_operator", "`operator_symbol` IN ('+', '-', 'x', '/')"),
        (
            "ck_question_answer_matches_operands",
            "(`operator_symbol` = '+' AND `expected_answer` = `left_operand` + `right_operand`) "
            "OR (`operator_symbol` = '-' AND `expected_answer` = `left_operand` - `right_operand`) "
            "OR (`operator_symbol` = 'x' AND `expected_answer` = `left_operand` * `right_operand`) "
            "OR (`operator_symbol` = '/' AND `right_operand` > 0 "
            "AND `left_operand` = `expected_answer` * `right_operand`)",
        ),
    ),
    "student_question_attempts": (
        ("ck_attempt_number_positive", "`attempt_number` >= 1"),
        (
            "ck_attempt_response_time_nonnegative",
            "`response_time_ms` IS NULL OR `response_time_ms` >= 0",
        ),
        (
            "ck_attempt_gesture_count_nonnegative",
            "`gesture_attempt_count` >= 0",
        ),
        ("ck_attempt_hint_boolean", "`hint_used` IN (0, 1)"),
        (
            "ck_attempt_submitted_answer_range",
            "`submitted_answer` IS NULL OR `submitted_answer` BETWEEN 0 AND 50",
        ),
        (
            "ck_attempt_status_consistency",
            "(`status` = 'completed' AND `submitted_answer` IS NOT NULL "
            "AND `is_correct` = 1 AND `skipped` = 0) "
            "OR (`status` = 'incorrect' AND `submitted_answer` IS NOT NULL "
            "AND `is_correct` = 0 AND `skipped` = 0) "
            "OR (`status` = 'skipped' AND `submitted_answer` IS NULL "
            "AND `is_correct` IS NULL AND `skipped` = 1) "
            "OR (`status` IN ('unanswered', 'invalid') AND `submitted_answer` IS NULL "
            "AND `is_correct` IS NULL AND `skipped` = 0)",
        ),
    ),
    "student_sign_recognition_logs": (
        (
            "ck_recognition_status",
            "`status` IN ('recognized', 'low_confidence', 'no_gesture', 'processing_failed')",
        ),
        (
            "ck_recognition_attempt_number_positive",
            "`recognition_attempt_number` >= 1",
        ),
        (
            "ck_recognition_predicted_range",
            "`predicted_value` IS NULL OR `predicted_value` BETWEEN 0 AND 50",
        ),
        (
            "ck_recognition_confidence_range",
            "`confidence` IS NULL OR `confidence` BETWEEN 0 AND 1",
        ),
        (
            "ck_recognition_status_consistency",
            "(`status` IN ('recognized', 'low_confidence') AND `gesture_detected` = 1 "
            "AND `predicted_value` IS NOT NULL AND `confidence` IS NOT NULL) "
            "OR (`status` IN ('no_gesture', 'processing_failed') AND `gesture_detected` = 0 "
            "AND `predicted_value` IS NULL AND `confidence` IS NULL)",
        ),
    ),
}


def _apply_constraints(table_name, constraints, create):
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch_op:
            for name, condition in constraints:
                if create:
                    batch_op.create_check_constraint(name, condition)
                else:
                    batch_op.drop_constraint(name, type_="check")
        return

    for name, condition in constraints:
        if create:
            op.create_check_constraint(name, table_name, condition)
        else:
            op.drop_constraint(name, table_name, type_="check")


def upgrade():
    for table_name, constraints in CHECK_CONSTRAINTS.items():
        _apply_constraints(table_name, constraints, create=True)


def downgrade():
    for table_name, constraints in reversed(tuple(CHECK_CONSTRAINTS.items())):
        _apply_constraints(table_name, constraints, create=False)
