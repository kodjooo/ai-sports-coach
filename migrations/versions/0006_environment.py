"""Среда и инвентарь: у упражнений и у пользователя

Revision ID: 0006_environment
Revises: 0005_plan_structure
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_environment"
down_revision: Union[str, None] = "0005_plan_structure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exercises", sa.Column("environment", sa.String(), nullable=True))
    op.add_column("exercises", sa.Column("equipment", sa.String(), nullable=True))
    op.add_column("users", sa.Column("environment", sa.String(), nullable=True))
    op.add_column("users", sa.Column("equipment", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "equipment")
    op.drop_column("users", "environment")
    op.drop_column("exercises", "equipment")
    op.drop_column("exercises", "environment")
