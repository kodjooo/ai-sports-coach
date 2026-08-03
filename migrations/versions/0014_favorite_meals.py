"""Избранные блюда (быстрая запись одной кнопкой)

Revision ID: 0014_favorite_meals
Revises: 0013_exercise_howto
Create Date: 2026-07-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_favorite_meals"
down_revision: Union[str, None] = "0013_exercise_howto"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "favorite_meals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dish", sa.String(), nullable=False),
        sa.Column("kcal", sa.Numeric(), nullable=True),
        sa.Column("payload", sa.String(), nullable=False),
        sa.Column("times_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_favorite_meals_user", "favorite_meals", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_favorite_meals_user", table_name="favorite_meals")
    op.drop_table("favorite_meals")
