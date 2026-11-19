"""Preserve timestamp precision on MySQL.

Revision ID: 0003_mysql_datetime_precision
Revises: 0002_question_retries
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision = "0003_mysql_datetime_precision"
down_revision = "0002_question_retries"
branch_labels = None
depends_on = None


DATETIME_COLUMNS = {
    "users": ("created_at",),
    "student_learning_sessions": ("started_at", "ended_at", "created_at"),
    "student_activity_attempts": ("started_at", "completed_at"),
    "learning_questions": ("displayed_at", "created_at"),
    "student_question_attempts": ("first_gesture_at", "attempted_at"),
    "student_sign_recognition_logs": ("recognized_at",),
}


def _set_datetime_precision(precision):
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return

    inspector = sa.inspect(bind)
    for table_name, column_names in DATETIME_COLUMNS.items():
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        for column_name in column_names:
            column = columns[column_name]
            if getattr(column["type"], "fsp", None) == precision:
                continue
            op.alter_column(
                table_name,
                column_name,
                existing_type=column["type"],
                type_=mysql.DATETIME(fsp=precision) if precision else mysql.DATETIME(),
                existing_nullable=column["nullable"],
            )


def upgrade():
    _set_datetime_precision(6)


def downgrade():
    _set_datetime_precision(0)
