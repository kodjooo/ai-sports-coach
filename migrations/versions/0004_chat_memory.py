"""Память диалога: окно сообщений и резюме переписки

Revision ID: 0004_chat_memory
Revises: 0003_train_time
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_chat_memory"
down_revision: Union[str, None] = "0003_train_time"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("chat_summary", sa.String(), nullable=True))
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("role", sa.String()),
        sa.Column("content", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_user", "chat_messages", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_user", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_column("users", "chat_summary")
