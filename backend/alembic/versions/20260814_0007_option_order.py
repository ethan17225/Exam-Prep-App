"""freeze per-attempt option order on in-progress exams

When shuffle is on, each attempt randomizes MCQ/SATA/cloze/bowtie/ranking
choices. That permutation is stored here so a resume does not reshuffle.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "in_progress_exam",
        sa.Column(
            "option_order",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("in_progress_exam", "option_order")
