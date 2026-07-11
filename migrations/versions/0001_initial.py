"""Начальная схема БД

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tg_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("name", sa.String()),
        sa.Column("weight_kg", sa.Numeric()),
        sa.Column("goal", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "exercises",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("muscle_group", sa.String()),
        sa.Column("difficulty", sa.Integer()),
        sa.Column("technique", sa.String()),
        sa.Column("variations", postgresql.JSONB()),
    )
    op.create_table(
        "workout_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("label", sa.String()),
        sa.Column("weekday", sa.Integer()),
        sa.Column("active", sa.Boolean(), server_default=sa.true()),
    )
    op.create_table(
        "template_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("template_id", sa.BigInteger(), sa.ForeignKey("workout_templates.id")),
        sa.Column("exercise_id", sa.BigInteger(), sa.ForeignKey("exercises.id")),
        sa.Column("target_sets", sa.Integer()),
        sa.Column("target_reps", sa.Integer()),
        sa.Column("order_idx", sa.Integer()),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("template_id", sa.BigInteger(), sa.ForeignKey("workout_templates.id")),
        sa.Column("planned_date", sa.Date()),
        sa.Column("status", sa.String()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "set_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("sessions.id")),
        sa.Column("exercise_id", sa.BigInteger(), sa.ForeignKey("exercises.id")),
        sa.Column("set_idx", sa.Integer()),
        sa.Column("reps", sa.Integer()),
        sa.Column("effort", sa.String()),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "weight_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("weight_kg", sa.Numeric()),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "meals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("photo_file_id", sa.String()),
        sa.Column("grams", sa.Numeric()),
        sa.Column("kcal_est", sa.Numeric()),
        sa.Column("note", sa.String()),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("meals")
    op.drop_table("weight_logs")
    op.drop_table("set_logs")
    op.drop_table("sessions")
    op.drop_table("template_items")
    op.drop_table("workout_templates")
    op.drop_table("exercises")
    op.drop_table("users")
