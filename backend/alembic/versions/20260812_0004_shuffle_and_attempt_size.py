"""exam shuffle flag and questions_per_attempt

`shuffle` defaults true so existing exams keep today's behaviour. `questions_per_attempt`
is nullable — null means "take every question".

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exam",
        sa.Column("shuffle", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("exam", sa.Column("questions_per_attempt", sa.Integer(), nullable=True))
    # Drop the default used only to backfill — future creates must set shuffle
    # explicitly (the schema/service always do).
    op.alter_column("exam", "shuffle", server_default=None)


def downgrade() -> None:
    op.drop_column("exam", "questions_per_attempt")
    op.drop_column("exam", "shuffle")
