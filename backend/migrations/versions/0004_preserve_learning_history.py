"""Prevent parent deletions from cascading through learning history.

Revision ID: 0004_preserve_learning_history
Revises: 0003_mysql_datetime_precision
"""
import sqlalchemy as sa
from alembic import op


revision = "0004_preserve_learning_history"
down_revision = "0003_mysql_datetime_precision"
branch_labels = None
depends_on = None


HISTORICAL_FOREIGN_KEYS = (
    ("student_learning_sessions", "student_id", "users"),
    ("student_activity_attempts", "student_id", "users"),
    ("student_activity_attempts", "session_id", "student_learning_sessions"),
    ("learning_questions", "activity_attempt_id", "student_activity_attempts"),
    ("student_question_attempts", "student_id", "users"),
    ("student_question_attempts", "session_id", "student_learning_sessions"),
    ("student_question_attempts", "activity_attempt_id", "student_activity_attempts"),
    ("student_sign_recognition_logs", "activity_attempt_id", "student_activity_attempts"),
)


def _replace_ondelete(table_name, column_name, referred_table, ondelete):
    bind = op.get_bind()
    foreign_keys = sa.inspect(bind).get_foreign_keys(table_name)
    foreign_key = next(
        (
            constraint
            for constraint in foreign_keys
            if constraint["constrained_columns"] == [column_name]
            and constraint["referred_table"] == referred_table
        ),
        None,
    )
    if foreign_key is None:
        raise RuntimeError(
            f"Missing foreign key {table_name}.{column_name} -> {referred_table}.id"
        )
    if (foreign_key.get("options", {}).get("ondelete") or "").upper() == ondelete:
        return

    constraint_name = (
        foreign_key.get("name")
        or f"fk_{table_name}_{column_name}_{referred_table}"
    )
    if bind.dialect.name == "sqlite":
        naming_convention = {
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        }
        with op.batch_alter_table(
            table_name,
            naming_convention=naming_convention,
        ) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="foreignkey")
            batch_op.create_foreign_key(
                constraint_name,
                referred_table,
                [column_name],
                ["id"],
                ondelete=ondelete,
            )
        return

    op.drop_constraint(constraint_name, table_name, type_="foreignkey")
    op.create_foreign_key(
        constraint_name,
        table_name,
        referred_table,
        [column_name],
        ["id"],
        ondelete=ondelete,
    )


def upgrade():
    for table_name, column_name, referred_table in HISTORICAL_FOREIGN_KEYS:
        _replace_ondelete(table_name, column_name, referred_table, "RESTRICT")


def downgrade():
    for table_name, column_name, referred_table in HISTORICAL_FOREIGN_KEYS:
        _replace_ondelete(table_name, column_name, referred_table, "CASCADE")
