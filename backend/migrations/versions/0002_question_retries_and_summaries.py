"""Allow multiple answer attempts per question and track activity summaries.

Revision ID: 0002_question_retries
Revises: 0001_learning_data
"""
import sqlalchemy as sa
from alembic import op


revision = "0002_question_retries"
down_revision = "0001_learning_data"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    activity_table = "student_activity_attempts"
    attempt_table = "student_question_attempts"
    inspector = sa.inspect(bind)

    for column in (
        sa.Column("total_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_questions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_questions", sa.Integer(), server_default="0", nullable=False),
    ):
        if column.name not in {item["name"] for item in inspector.get_columns(activity_table)}:
            op.add_column(activity_table, column)

    recognition_columns = {
        item["name"] for item in inspector.get_columns("student_sign_recognition_logs")
    }
    if "model_key" not in recognition_columns:
        op.add_column(
            "student_sign_recognition_logs",
            sa.Column("model_key", sa.String(length=32), nullable=True),
        )

    unique_question_constraint = next(
        (
            constraint
            for constraint in inspector.get_unique_constraints(attempt_table)
            if constraint.get("column_names") == ["question_id"]
        ),
        None,
    )
    question_index_exists = any(
        index.get("column_names") == ["question_id"] and not index.get("unique")
        for index in inspector.get_indexes(attempt_table)
    )
    if bind.dialect.name == "sqlite" and unique_question_constraint:
        with op.batch_alter_table(
            attempt_table,
            naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"},
        ) as batch_op:
            batch_op.drop_constraint(
                unique_question_constraint.get("name")
                or "uq_student_question_attempts_question_id",
                type_="unique",
            )
            if not question_index_exists:
                batch_op.create_index("ix_student_question_attempts_question_id", ["question_id"])
    elif bind.dialect.name != "sqlite" and unique_question_constraint:
        op.drop_constraint(
            unique_question_constraint.get("name") or "question_id",
            attempt_table,
            type_="unique",
        )
        question_index_exists = any(
            index.get("column_names") == ["question_id"] and not index.get("unique")
            for index in sa.inspect(bind).get_indexes(attempt_table)
        )
        if not question_index_exists:
            op.create_index(
                "ix_student_question_attempts_question_id",
                attempt_table,
                ["question_id"],
            )
    if not unique_question_constraint and not question_index_exists:
        op.create_index(
            "ix_student_question_attempts_question_id",
            attempt_table,
            ["question_id"],
        )

    op.execute(
        """
        UPDATE student_activity_attempts
        SET total_questions = (
                SELECT COUNT(*)
                FROM learning_questions
                WHERE learning_questions.activity_attempt_id = student_activity_attempts.id
            ),
            total_attempts = (
                SELECT COUNT(*)
                FROM student_question_attempts
                WHERE student_question_attempts.activity_attempt_id = student_activity_attempts.id
                    AND student_question_attempts.is_correct IS NOT NULL
            ),
            completed_questions = (
                SELECT COUNT(DISTINCT question_id)
                FROM student_question_attempts
                WHERE student_question_attempts.activity_attempt_id = student_activity_attempts.id
                    AND student_question_attempts.is_correct = 1
            ),
            skipped_questions = (
                SELECT COUNT(*)
                FROM student_question_attempts
                WHERE student_question_attempts.activity_attempt_id = student_activity_attempts.id
                    AND student_question_attempts.skipped = 1
            ),
            correct_answers = (
                SELECT COUNT(*)
                FROM student_question_attempts
                WHERE student_question_attempts.activity_attempt_id = student_activity_attempts.id
                    AND student_question_attempts.is_correct = 1
            ),
            incorrect_answers = (
                SELECT COUNT(*)
                FROM student_question_attempts
                WHERE student_question_attempts.activity_attempt_id = student_activity_attempts.id
                    AND student_question_attempts.is_correct = 0
            )
        """
    )


def downgrade():
    bind = op.get_bind()
    attempt_table = "student_question_attempts"
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(
            attempt_table,
            naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"},
        ) as batch_op:
            batch_op.drop_index("ix_student_question_attempts_question_id")
            batch_op.create_unique_constraint(
                "uq_student_question_attempts_question_id",
                ["question_id"],
            )
    else:
        op.drop_index("ix_student_question_attempts_question_id", table_name=attempt_table)
        op.create_unique_constraint("question_id", attempt_table, ["question_id"])

    op.drop_column("student_activity_attempts", "skipped_questions")
    op.drop_column("student_activity_attempts", "completed_questions")
    op.drop_column("student_activity_attempts", "total_attempts")
    op.drop_column("student_sign_recognition_logs", "model_key")
