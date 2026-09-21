"""question banks, sections, and per-attempt section shares

Questions may belong to an exam or a bank section, never both. Bank-backed exams
store a percent per section; the attempt draws that mix on first save.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.identifiers import ID_LENGTH

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "question_bank",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("owner_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("course_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["course.id"], name="question_bank_course_id_fkey", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], name="question_bank_owner_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="question_bank_pkey"),
    )
    op.create_index("question_bank_owner_id_idx", "question_bank", ["owner_id"])

    op.create_table(
        "bank_section",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("bank_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["bank_id"], ["question_bank.id"], name="bank_section_bank_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="bank_section_pkey"),
    )
    op.create_index("bank_section_bank_id_idx", "bank_section", ["bank_id"])

    op.add_column(
        "exam",
        sa.Column("bank_id", sa.String(length=ID_LENGTH), nullable=True),
    )
    op.create_foreign_key(
        "exam_bank_id_fkey",
        "exam",
        "question_bank",
        ["bank_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("exam_bank_id_idx", "exam", ["bank_id"])

    op.create_table(
        "exam_section_share",
        sa.Column("exam_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("section_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], name="exam_section_share_exam_id_fkey", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["section_id"], ["bank_section.id"], name="exam_section_share_section_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("exam_id", "section_id", name="exam_section_share_pkey"),
    )
    op.create_index("exam_section_share_section_id_idx", "exam_section_share", ["section_id"])

    op.add_column("question", sa.Column("section_id", sa.String(length=ID_LENGTH), nullable=True))
    op.alter_column("question", "exam_id", existing_type=sa.String(length=ID_LENGTH), nullable=True)
    op.create_foreign_key(
        "question_section_id_fkey",
        "question",
        "bank_section",
        ["section_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("question_section_id_idx", "question", ["section_id"])
    op.create_check_constraint(
        "exam_xor_section",
        "question",
        "(exam_id IS NULL) != (section_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("question_exam_xor_section_check", "question", type_="check")
    op.drop_index("question_section_id_idx", table_name="question")
    op.drop_constraint("question_section_id_fkey", "question", type_="foreignkey")
    op.drop_column("question", "section_id")
    op.alter_column("question", "exam_id", existing_type=sa.String(length=ID_LENGTH), nullable=False)

    op.drop_index("exam_section_share_section_id_idx", table_name="exam_section_share")
    op.drop_table("exam_section_share")

    op.drop_index("exam_bank_id_idx", table_name="exam")
    op.drop_constraint("exam_bank_id_fkey", "exam", type_="foreignkey")
    op.drop_column("exam", "bank_id")

    op.drop_index("bank_section_bank_id_idx", table_name="bank_section")
    op.drop_table("bank_section")
    op.drop_index("question_bank_owner_id_idx", table_name="question_bank")
    op.drop_table("question_bank")
