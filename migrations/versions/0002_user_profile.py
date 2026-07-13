"""Персональный профиль пользователя: system_prompt и profile_summary

Revision ID: 0002_user_profile
Revises: 0001_initial
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_user_profile"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("system_prompt", sa.String(), nullable=True))
    op.add_column("users", sa.Column("profile_summary", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profile_summary")
    op.drop_column("users", "system_prompt")
