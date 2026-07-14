"""Питание: профиль (пол/возраст/активность), БЖУ у meals, таблица meal_items

Revision ID: 0008_nutrition
Revises: 0007_height
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_nutrition"
down_revision: Union[str, None] = "0007_height"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("sex", sa.String(), nullable=True))
    op.add_column("users", sa.Column("age", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("activity", sa.String(), nullable=True))

    op.add_column("meals", sa.Column("kcal", sa.Numeric(), nullable=True))
    op.add_column("meals", sa.Column("protein", sa.Numeric(), nullable=True))
    op.add_column("meals", sa.Column("fat", sa.Numeric(), nullable=True))
    op.add_column("meals", sa.Column("carbs", sa.Numeric(), nullable=True))

    op.create_table(
        "meal_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("meal_id", sa.BigInteger(), sa.ForeignKey("meals.id")),
        sa.Column("name", sa.String()),
        sa.Column("grams", sa.Numeric()),
        sa.Column("kcal", sa.Numeric()),
        sa.Column("protein", sa.Numeric()),
        sa.Column("fat", sa.Numeric()),
        sa.Column("carbs", sa.Numeric()),
    )


def downgrade() -> None:
    op.drop_table("meal_items")
    op.drop_column("meals", "carbs")
    op.drop_column("meals", "fat")
    op.drop_column("meals", "protein")
    op.drop_column("meals", "kcal")
    op.drop_column("users", "activity")
    op.drop_column("users", "age")
    op.drop_column("users", "sex")
