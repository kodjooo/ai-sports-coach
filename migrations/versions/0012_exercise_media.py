"""Медиа упражнений (GIF, EN-версия) и фаза элемента плана

Revision ID: 0012_exercise_media
Revises: 0011_kcal_burned
Create Date: 2026-07-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_exercise_media"
down_revision: Union[str, None] = "0011_kcal_burned"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exercises", sa.Column("gif", sa.String(), nullable=True))
    op.add_column("exercises", sa.Column("name_en", sa.String(), nullable=True))
    op.add_column("exercises", sa.Column("technique_en", sa.String(), nullable=True))
    op.add_column(
        "template_items",
        sa.Column("phase", sa.String(), nullable=False, server_default="main"),
    )


def downgrade() -> None:
    op.drop_column("template_items", "phase")
    op.drop_column("exercises", "technique_en")
    op.drop_column("exercises", "name_en")
    op.drop_column("exercises", "gif")
