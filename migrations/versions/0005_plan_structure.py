"""Структура плана: разминка/заминка у дня и отдых у упражнения

Revision ID: 0005_plan_structure
Revises: 0004_chat_memory
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_plan_structure"
down_revision: Union[str, None] = "0004_chat_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workout_templates", sa.Column("warmup", sa.String(), nullable=True))
    op.add_column("workout_templates", sa.Column("cooldown", sa.String(), nullable=True))
    op.add_column("template_items", sa.Column("rest_sec", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("template_items", "rest_sec")
    op.drop_column("workout_templates", "cooldown")
    op.drop_column("workout_templates", "warmup")
