"""Рост пользователя

Revision ID: 0007_height
Revises: 0006_environment
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_height"
down_revision: Union[str, None] = "0006_environment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("height_cm", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "height_cm")
