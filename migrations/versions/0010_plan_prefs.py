"""Настройки: упражнений в день и режим питания

Revision ID: 0010_plan_prefs
Revises: 0009_user_level
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_plan_prefs"
down_revision: Union[str, None] = "0009_user_level"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("exercises_per_day", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("nutrition_goal", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "nutrition_goal")
    op.drop_column("users", "exercises_per_day")
