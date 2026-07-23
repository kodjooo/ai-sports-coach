"""Готовое описание «как правильно» для упражнений (кнопка без вызова LLM)

Revision ID: 0013_exercise_howto
Revises: 0012_exercise_media
Create Date: 2026-07-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_exercise_howto"
down_revision: Union[str, None] = "0012_exercise_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exercises", sa.Column("howto", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("exercises", "howto")
