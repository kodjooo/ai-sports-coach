"""Нелюбимые упражнения пользователя («больше не предлагать»)

Revision ID: 0015_user_disliked
Revises: 0014_favorite_meals
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_user_disliked"
down_revision: Union[str, None] = "0014_favorite_meals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("disliked", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "disliked")
