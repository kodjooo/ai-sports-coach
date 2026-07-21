"""Уровень подготовки пользователя

Revision ID: 0009_user_level
Revises: 0008_nutrition
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_user_level"
down_revision: Union[str, None] = "0008_nutrition"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("level", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "level")
