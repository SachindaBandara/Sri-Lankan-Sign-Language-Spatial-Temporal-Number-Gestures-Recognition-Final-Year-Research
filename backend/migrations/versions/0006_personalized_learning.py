"""Persist personalized learning progress and guidance.

Revision ID: 0006_personalized_learning
Revises: 0005_learning_data_checks
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision = "0006_personalized_learning"
down_revision = "0005_learning_data_checks"
branch_labels = None
depends_on = None

DATETIME_TYPE = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade():
    op.create_table(
        "student_learning_progress",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("current_difficulty", sa.String(length=24), nullable=False),
        sa.Column("total_attempts", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("incorrect_answers", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("recent_accuracy", sa.Float(), nullable=True),
        sa.Column("average_response_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("improvement_rate", sa.Float(), nullable=True),
        sa.Column("recognition_events", sa.Integer(), nullable=False),
        sa.Column("high_confidence_recognitions", sa.Integer(), nullable=False),
        sa.Column("average_recognition_confidence", sa.Float(), nullable=True),
        sa.Column("last_evaluated_attempt_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", DATETIME_TYPE, nullable=False),
        sa.CheckConstraint(
            "`operation_type` IN "
            "('number_identification', 'addition', 'subtraction', 'multiplication', 'division')",
            name="ck_learning_progress_operation",
        ),
        sa.CheckConstraint(
            "`current_difficulty` IN ('easy', 'standard', 'hard')",
            name="ck_learning_progress_difficulty",
        ),
        sa.CheckConstraint(
            "`total_attempts` >= 0 AND `correct_answers` >= 0 "
            "AND `incorrect_answers` >= 0 AND `recognition_events` >= 0 "
            "AND `high_confidence_recognitions` >= 0 "
            "AND `correct_answers` + `incorrect_answers` = `total_attempts` "
            "AND `high_confidence_recognitions` <= `recognition_events` "
            "AND `last_evaluated_attempt_id` >= 0",
            name="ck_learning_progress_counts",
        ),
        sa.CheckConstraint(
            "`average_response_time_ms` IS NULL OR `average_response_time_ms` >= 0",
            name="ck_learning_progress_response_time",
        ),
        sa.CheckConstraint(
            "`improvement_rate` IS NULL OR `improvement_rate` BETWEEN -1 AND 1",
            name="ck_learning_progress_improvement_rate",
        ),
        sa.CheckConstraint(
            "`accuracy` IS NULL OR `accuracy` BETWEEN 0 AND 1",
            name="ck_learning_progress_accuracy",
        ),
        sa.CheckConstraint(
            "`recent_accuracy` IS NULL OR `recent_accuracy` BETWEEN 0 AND 1",
            name="ck_learning_progress_recent_accuracy",
        ),
        sa.CheckConstraint(
            "`average_recognition_confidence` IS NULL "
            "OR `average_recognition_confidence` BETWEEN 0 AND 1",
            name="ck_learning_progress_recognition_confidence",
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id", "operation_type",
            name="uq_learning_progress_student_operation",
        ),
    )
    op.create_index(
        "ix_student_learning_progress_student_id",
        "student_learning_progress",
        ["student_id"],
    )

    op.create_table(
        "student_difficulty_adjustments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("previous_difficulty", sa.String(length=24), nullable=False),
        sa.Column("new_difficulty", sa.String(length=24), nullable=False),
        sa.Column("recent_accuracy", sa.Float(), nullable=False),
        sa.Column("historical_accuracy", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=False),
        sa.Column("created_at", DATETIME_TYPE, nullable=False),
        sa.CheckConstraint(
            "`operation_type` IN ('addition', 'subtraction', 'multiplication', 'division')",
            name="ck_difficulty_adjustment_operation",
        ),
        sa.CheckConstraint(
            "`previous_difficulty` IN ('easy', 'standard', 'hard') "
            "AND `new_difficulty` IN ('easy', 'standard', 'hard') "
            "AND `previous_difficulty` <> `new_difficulty`",
            name="ck_difficulty_adjustment_levels",
        ),
        sa.CheckConstraint(
            "`recent_accuracy` BETWEEN 0 AND 1 AND `historical_accuracy` BETWEEN 0 AND 1",
            name="ck_difficulty_adjustment_accuracy",
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_student_difficulty_adjustments_student_id",
        "student_difficulty_adjustments",
        ["student_id"],
    )

    op.create_table(
        "student_learning_recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("recommendation_key", sa.String(length=96), nullable=False),
        sa.Column("difficulty_level", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("explanation", sa.String(length=500), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("baseline_accuracy", sa.Float(), nullable=True),
        sa.Column("created_at", DATETIME_TYPE, nullable=False),
        sa.Column("updated_at", DATETIME_TYPE, nullable=False),
        sa.Column("completed_at", DATETIME_TYPE, nullable=True),
        sa.CheckConstraint(
            "`operation_type` IN "
            "('number_identification', 'addition', 'subtraction', 'multiplication', 'division')",
            name="ck_recommendation_operation",
        ),
        sa.CheckConstraint(
            "`difficulty_level` IN ('easy', 'standard', 'hard')",
            name="ck_recommendation_difficulty",
        ),
        sa.CheckConstraint(
            "`operation_type` <> 'number_identification' OR `difficulty_level` = 'standard'",
            name="ck_recommendation_number_difficulty",
        ),
        sa.CheckConstraint(
            "`status` IN ('pending', 'in_progress', 'completed', 'dismissed')",
            name="ck_recommendation_status",
        ),
        sa.CheckConstraint("`priority` BETWEEN 1 AND 5", name="ck_recommendation_priority"),
        sa.CheckConstraint(
            "`baseline_accuracy` IS NULL OR `baseline_accuracy` BETWEEN 0 AND 1",
            name="ck_recommendation_baseline_accuracy",
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id", "recommendation_key",
            name="uq_recommendation_student_key",
        ),
    )
    op.create_index(
        "ix_student_learning_recommendations_student_id",
        "student_learning_recommendations",
        ["student_id"],
    )

    op.create_table(
        "student_learning_paths",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", DATETIME_TYPE, nullable=False),
        sa.Column("updated_at", DATETIME_TYPE, nullable=False),
        sa.CheckConstraint(
            "`status` IN ('active', 'completed')",
            name="ck_learning_path_status",
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id"),
    )

    op.create_table(
        "student_learning_path_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("path_id", sa.Integer(), nullable=False),
        sa.Column("sequence_number", sa.SmallInteger(), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("difficulty_level", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("completed_at", DATETIME_TYPE, nullable=True),
        sa.CheckConstraint(
            "`sequence_number` >= 1",
            name="ck_learning_path_step_sequence",
        ),
        sa.CheckConstraint(
            "`operation_type` IN "
            "('number_identification', 'addition', 'subtraction', 'multiplication', 'division')",
            name="ck_learning_path_step_operation",
        ),
        sa.CheckConstraint(
            "`difficulty_level` IN ('easy', 'standard', 'hard')",
            name="ck_learning_path_step_difficulty",
        ),
        sa.CheckConstraint(
            "`operation_type` <> 'number_identification' OR `difficulty_level` = 'standard'",
            name="ck_learning_path_step_number_difficulty",
        ),
        sa.CheckConstraint(
            "`status` IN ('locked', 'in_progress', 'completed')",
            name="ck_learning_path_step_status",
        ),
        sa.ForeignKeyConstraint(["path_id"], ["student_learning_paths.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "path_id", "operation_type",
            name="uq_learning_path_step_operation",
        ),
        sa.UniqueConstraint(
            "path_id", "sequence_number",
            name="uq_learning_path_step_sequence",
        ),
    )
    op.create_index(
        "ix_student_learning_path_steps_path_id",
        "student_learning_path_steps",
        ["path_id"],
    )


def downgrade():
    op.drop_index(
        "ix_student_learning_path_steps_path_id",
        table_name="student_learning_path_steps",
    )
    op.drop_table("student_learning_path_steps")
    op.drop_table("student_learning_paths")
    op.drop_index(
        "ix_student_learning_recommendations_student_id",
        table_name="student_learning_recommendations",
    )
    op.drop_table("student_learning_recommendations")
    op.drop_index(
        "ix_student_difficulty_adjustments_student_id",
        table_name="student_difficulty_adjustments",
    )
    op.drop_table("student_difficulty_adjustments")
    op.drop_index(
        "ix_student_learning_progress_student_id",
        table_name="student_learning_progress",
    )
    op.drop_table("student_learning_progress")
