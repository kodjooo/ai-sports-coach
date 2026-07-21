"""Оценка потраченных калорий за тренировку

Revision ID: 0011_kcal_burned
Revises: 0010_plan_prefs
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_kcal_burned"
down_revision: Union[str, None] = "0010_plan_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("kcal_burned", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "kcal_burned")
