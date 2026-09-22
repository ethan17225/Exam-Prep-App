"""exam and bank collaborator tables

Instructor-to-instructor collaboration on a shared exam row. Sharing a
bank-backed exam also grants write access to that question bank.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.identifiers import ID_LENGTH

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exam_collaborator",
        sa.Column("exam_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("user_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("invited_by", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], name="exam_collaborator_exam_id_fkey", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="exam_collaborator_user_id_fkey", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_by"], ["user.id"], name="exam_collaborator_invited_by_fkey", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("exam_id", "user_id", name="exam_collaborator_pkey"),
    )
    op.create_index("exam_collaborator_user_id_idx", "exam_collaborator", ["user_id"])

    op.create_table(
        "bank_collaborator",
        sa.Column("bank_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("user_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("invited_by", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bank_id"], ["question_bank.id"], name="bank_collaborator_bank_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="bank_collaborator_user_id_fkey", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_by"], ["user.id"], name="bank_collaborator_invited_by_fkey", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("bank_id", "user_id", name="bank_collaborator_pkey"),
    )
    op.create_index("bank_collaborator_user_id_idx", "bank_collaborator", ["user_id"])


def downgrade() -> None:
    op.drop_index("bank_collaborator_user_id_idx", table_name="bank_collaborator")
    op.drop_table("bank_collaborator")
    op.drop_index("exam_collaborator_user_id_idx", table_name="exam_collaborator")
    op.drop_table("exam_collaborator")
