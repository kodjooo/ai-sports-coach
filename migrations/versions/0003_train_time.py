"""Время тренировки пользователя для напоминаний

Revision ID: 0003_train_time
Revises: 0002_user_profile
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_train_time"
down_revision: Union[str, None] = "0002_user_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("train_hour", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("train_minute", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "train_minute")
    op.drop_column("users", "train_hour")
