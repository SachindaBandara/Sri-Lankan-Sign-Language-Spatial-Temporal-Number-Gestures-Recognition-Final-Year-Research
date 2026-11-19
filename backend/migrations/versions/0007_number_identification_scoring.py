"""Persist prompted number-identification answers and correctness.

Revision ID: 0007_number_identification_scoring
Revises: 0006_personalized_learning
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision = "0007_number_identification_scoring"
down_revision = "0006_personalized_learning"
branch_labels = None
depends_on = None

DATETIME_TYPE = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def _inspector():
    return sa.inspect(op.get_bind())


def _has_index(table_name, index_name):
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _has_column(table_name, column_name):
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_foreign_key(table_name, constraint_name):
    return any(
        foreign_key["name"] == constraint_name
        for foreign_key in _inspector().get_foreign_keys(table_name)
    )


def _has_check_constraint(table_name, constraint_name):
    return any(
        constraint["name"] == constraint_name
        for constraint in _inspector().get_check_constraints(table_name)
    )


def _drop_check_constraint_if_present(table_name, constraint_name):
    if _has_check_constraint(table_name, constraint_name):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="check")


def upgrade():
    if not _inspector().has_table("number_identification_questions"):
        op.create_table(
            "number_identification_questions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("activity_attempt_id", sa.Integer(), nullable=False),
            sa.Column("sequence_number", sa.SmallInteger(), nullable=False),
            sa.Column("expected_value", sa.SmallInteger(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_at", DATETIME_TYPE, nullable=False),
            sa.Column("completed_at", DATETIME_TYPE, nullable=True),
            sa.CheckConstraint(
                "`expected_value` BETWEEN 0 AND 50",
                name="ck_number_question_expected_value",
            ),
            sa.CheckConstraint(
                "`sequence_number` >= 1",
                name="ck_number_question_sequence",
            ),
            sa.CheckConstraint(
                "`status` IN ('in_progress', 'completed', 'skipped')",
                name="ck_number_question_status",
            ),
            sa.ForeignKeyConstraint(
                ["activity_attempt_id"],
                ["student_activity_attempts.id"],
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "activity_attempt_id",
                "sequence_number",
                name="uq_number_question_activity_sequence",
            ),
        )
    if not _has_index(
        "number_identification_questions",
        "ix_number_identification_questions_activity_attempt_id",
    ):
        op.create_index(
            "ix_number_identification_questions_activity_attempt_id",
            "number_identification_questions",
            ["activity_attempt_id"],
        )

    if not _has_column("student_sign_recognition_logs", "number_question_id"):
        with op.batch_alter_table("student_sign_recognition_logs") as batch_op:
            batch_op.add_column(sa.Column("number_question_id", sa.String(length=36), nullable=True))
    if not _has_column("student_sign_recognition_logs", "is_correct"):
        with op.batch_alter_table("student_sign_recognition_logs") as batch_op:
            batch_op.add_column(sa.Column("is_correct", sa.Boolean(), nullable=True))
    _drop_check_constraint_if_present(
        "student_sign_recognition_logs",
        "ck_recognition_single_question",
    )
    if not _has_foreign_key("student_sign_recognition_logs", "fk_recognition_number_question"):
        with op.batch_alter_table("student_sign_recognition_logs") as batch_op:
            batch_op.create_foreign_key(
                "fk_recognition_number_question",
                "number_identification_questions",
                ["number_question_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    if not _has_check_constraint(
        "student_sign_recognition_logs",
        "ck_recognition_number_answer_consistency",
    ):
        with op.batch_alter_table("student_sign_recognition_logs") as batch_op:
            batch_op.create_check_constraint(
                "ck_recognition_number_answer_consistency",
                "`is_correct` IS NULL OR "
                "(`status` = 'recognized' AND `number_question_id` IS NOT NULL)",
            )
    if not _has_index(
        "student_sign_recognition_logs",
        "ix_student_sign_recognition_logs_number_question_id",
    ):
        with op.batch_alter_table("student_sign_recognition_logs") as batch_op:
            batch_op.create_index(
                "ix_student_sign_recognition_logs_number_question_id",
                ["number_question_id"],
            )


def downgrade():
    with op.batch_alter_table("student_sign_recognition_logs") as batch_op:
        batch_op.drop_index("ix_student_sign_recognition_logs_number_question_id")
        batch_op.drop_constraint(
            "ck_recognition_number_answer_consistency",
            type_="check",
        )
        batch_op.drop_constraint("fk_recognition_number_question", type_="foreignkey")
        batch_op.drop_column("is_correct")
        batch_op.drop_column("number_question_id")

    op.drop_index(
        "ix_number_identification_questions_activity_attempt_id",
        table_name="number_identification_questions",
    )
    op.drop_table("number_identification_questions")
