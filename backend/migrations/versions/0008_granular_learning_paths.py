"""Support multiple skill-level steps per learning path.

Revision ID: 0008_granular_learning_paths
Revises: 0007_number_identification_scoring
"""
import sqlalchemy as sa
from alembic import op


revision = "0008_granular_learning_paths"
down_revision = "0007_number_identification_scoring"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "student_learning_path_steps",
        sa.Column("skill_key", sa.String(length=64), nullable=True),
    )
    path_steps = sa.table(
        "student_learning_path_steps",
        sa.column("id", sa.Integer),
        sa.column("operation_type", sa.String),
        sa.column("skill_key", sa.String),
        sa.column("difficulty_level", sa.String),
    )
    connection = op.get_bind()
    existing_steps = connection.execute(
        sa.select(path_steps.c.id, path_steps.c.operation_type)
    ).mappings()
    for step in existing_steps:
        skill_key = (
            "number_identification_0_9"
            if step["operation_type"] == "number_identification"
            else f'{step["operation_type"]}_easy'
        )
        connection.execute(
            path_steps.update()
            .where(path_steps.c.id == step["id"])
            .values(
                skill_key=skill_key,
                difficulty_level=(
                    "standard"
                    if step["operation_type"] == "number_identification"
                    else "easy"
                ),
            )
        )

    with op.batch_alter_table("student_learning_path_steps") as batch_op:
        batch_op.alter_column(
            "skill_key",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch_op.drop_constraint(
            "uq_learning_path_step_operation",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_learning_path_step_skill",
            ["path_id", "skill_key"],
        )


def downgrade():
    with op.batch_alter_table("student_learning_path_steps") as batch_op:
        batch_op.drop_constraint("uq_learning_path_step_skill", type_="unique")
        batch_op.create_unique_constraint(
            "uq_learning_path_step_operation",
            ["path_id", "operation_type"],
        )
        batch_op.drop_column("skill_key")
