"""Create the frozen initial learning-data schema.

This revision is intentionally independent of current ORM models.

Revision ID: 0001_learning_data
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_learning_data"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("grade", sa.SmallInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "teacher_students",
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["teacher_id"], ["users.id"], name="fk_teacher_students_teacher", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name="fk_teacher_students_student", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("teacher_id", "student_id"),
    )

    op.create_table(
        "student_learning_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("identifier", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("total_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name="fk_learning_sessions_student", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identifier", name="uq_learning_sessions_identifier"),
    )
    op.create_index(
        "ix_student_learning_sessions_student_id",
        "student_learning_sessions",
        ["student_id"],
    )

    op.create_table(
        "student_activity_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_key", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("difficulty_level", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("incorrect_answers", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["student_learning_sessions.id"],
            name="fk_activity_attempts_session", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name="fk_activity_attempts_student", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_key", name="uq_activity_attempts_request_key"),
    )
    op.create_index(
        "ix_student_activity_attempts_student_id",
        "student_activity_attempts",
        ["student_id"],
    )
    op.create_index(
        "ix_student_activity_attempts_session_id",
        "student_activity_attempts",
        ["session_id"],
    )
    op.create_index(
        "ix_student_activity_attempts_operation_type",
        "student_activity_attempts",
        ["operation_type"],
    )

    op.create_table(
        "learning_questions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("activity_attempt_id", sa.Integer(), nullable=False),
        sa.Column("question_content", sa.String(length=160), nullable=False),
        sa.Column("left_operand", sa.Integer(), nullable=False),
        sa.Column("right_operand", sa.Integer(), nullable=False),
        sa.Column("operator_symbol", sa.String(length=4), nullable=False),
        sa.Column("question_type", sa.String(length=24), nullable=False),
        sa.Column("expected_answer", sa.Integer(), nullable=False),
        sa.Column("displayed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_attempt_id"],
            ["student_activity_attempts.id"],
            name="fk_learning_questions_activity",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_learning_questions_activity_attempt_id",
        "learning_questions",
        ["activity_attempt_id"],
    )

    op.create_table(
        "student_question_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("activity_attempt_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("expected_answer", sa.Integer(), nullable=False),
        sa.Column("submitted_answer", sa.Integer(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("response_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("first_gesture_at", sa.DateTime(), nullable=True),
        sa.Column("gesture_attempt_count", sa.Integer(), nullable=False),
        sa.Column("hint_used", sa.Boolean(), nullable=False),
        sa.Column("skipped", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_attempt_id"],
            ["student_activity_attempts.id"],
            name="fk_question_attempts_activity",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["learning_questions.id"],
            name="fk_question_attempts_question", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["student_learning_sessions.id"],
            name="fk_question_attempts_session",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name="fk_question_attempts_student", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_question_attempts_idempotency_key"),
        sa.UniqueConstraint("question_id", name="uq_student_question_attempts_question_id"),
    )
    op.create_index(
        "ix_student_question_attempts_student_id",
        "student_question_attempts",
        ["student_id"],
    )
    op.create_index(
        "ix_student_question_attempts_session_id",
        "student_question_attempts",
        ["session_id"],
    )
    op.create_index(
        "ix_student_question_attempts_activity_attempt_id",
        "student_question_attempts",
        ["activity_attempt_id"],
    )

    op.create_table(
        "student_sign_recognition_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_attempt_id", sa.Integer(), nullable=False),
        sa.Column("question_attempt_id", sa.Integer(), nullable=True),
        sa.Column("learning_question_id", sa.String(length=36), nullable=True),
        sa.Column("recognition_token_id", sa.String(length=36), nullable=True),
        sa.Column("predicted_value", sa.SmallInteger(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("gesture_detected", sa.Boolean(), nullable=False),
        sa.Column("recognition_attempt_number", sa.Integer(), nullable=False),
        sa.Column("recognized_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_attempt_id"],
            ["student_activity_attempts.id"],
            name="fk_recognition_logs_activity",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["learning_question_id"],
            ["learning_questions.id"],
            name="fk_recognition_logs_question",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["question_attempt_id"],
            ["student_question_attempts.id"],
            name="fk_recognition_logs_question_attempt",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_student_sign_recognition_logs_activity_attempt_id",
        "student_sign_recognition_logs",
        ["activity_attempt_id"],
    )
    op.create_index(
        "ix_student_sign_recognition_logs_question_attempt_id",
        "student_sign_recognition_logs",
        ["question_attempt_id"],
    )
    op.create_index(
        "ix_student_sign_recognition_logs_learning_question_id",
        "student_sign_recognition_logs",
        ["learning_question_id"],
    )
    op.create_index(
        "ix_student_sign_recognition_logs_recognition_token_id",
        "student_sign_recognition_logs",
        ["recognition_token_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_student_sign_recognition_logs_recognition_token_id", table_name="student_sign_recognition_logs")
    op.drop_index("ix_student_sign_recognition_logs_learning_question_id", table_name="student_sign_recognition_logs")
    op.drop_index("ix_student_sign_recognition_logs_question_attempt_id", table_name="student_sign_recognition_logs")
    op.drop_index("ix_student_sign_recognition_logs_activity_attempt_id", table_name="student_sign_recognition_logs")
    op.drop_table("student_sign_recognition_logs")
    op.drop_index("ix_student_question_attempts_activity_attempt_id", table_name="student_question_attempts")
    op.drop_index("ix_student_question_attempts_session_id", table_name="student_question_attempts")
    op.drop_index("ix_student_question_attempts_student_id", table_name="student_question_attempts")
    op.drop_table("student_question_attempts")
    op.drop_index("ix_learning_questions_activity_attempt_id", table_name="learning_questions")
    op.drop_table("learning_questions")
    op.drop_index("ix_student_activity_attempts_operation_type", table_name="student_activity_attempts")
    op.drop_index("ix_student_activity_attempts_session_id", table_name="student_activity_attempts")
    op.drop_index("ix_student_activity_attempts_student_id", table_name="student_activity_attempts")
    op.drop_table("student_activity_attempts")
    op.drop_index("ix_student_learning_sessions_student_id", table_name="student_learning_sessions")
    op.drop_table("student_learning_sessions")
    op.drop_table("teacher_students")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
