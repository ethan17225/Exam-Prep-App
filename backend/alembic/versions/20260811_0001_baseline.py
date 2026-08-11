"""baseline schema

Single collapsed baseline: the database was empty when the domain refactor
landed, so there is no history worth preserving. Constraint and index names are
the ones `POSTGRES_INDEXES_NAMING_CONVENTION` generates — do not hand-name them
differently or autogenerate will churn forever.

Table order matters: foreign keys reference tables created earlier.

Revision ID: 0001
Revises:
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # "user" is a Postgres reserved word; SQLAlchemy quotes it automatically.
    op.create_table(
        "user",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=60), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="user_pkey"),
        sa.UniqueConstraint("email", name="user_email_key"),
    )

    op.create_table(
        "course",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("owner_id", sa.String(length=8), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], name="course_owner_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="course_pkey"),
        # Course names are unique per owner, not globally.
        sa.UniqueConstraint("owner_id", "name", name="course_owner_id_name_key"),
    )
    op.create_index("course_owner_id_idx", "course", ["owner_id"])

    op.create_table(
        "exam",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("owner_id", sa.String(length=8), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("course_id", sa.String(length=8), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["course.id"], name="exam_course_id_fkey", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], name="exam_owner_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="exam_pkey"),
    )
    op.create_index("exam_course_id_idx", "exam", ["course_id"])
    op.create_index("exam_owner_id_idx", "exam", ["owner_id"])

    op.create_table(
        "question",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("exam_id", sa.String(length=8), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("answer", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("image", sa.Text(), nullable=True),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], name="question_exam_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="question_pkey"),
    )
    op.create_index("question_exam_id_idx", "question", ["exam_id"])

    op.create_table(
        "in_progress_exam",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("user_id", sa.String(length=8), nullable=False),
        sa.Column("exam_id", sa.String(length=8), nullable=False),
        sa.Column("exam_title", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column(
            "answers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "flagged",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "question_order",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("remaining_seconds", sa.Integer(), nullable=False),
        sa.Column("current_page", sa.Integer(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("answered_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("saved_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], name="in_progress_exam_exam_id_fkey", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="in_progress_exam_user_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="in_progress_exam_pkey"),
        # The autosave upsert depends on this constraint existing.
        sa.UniqueConstraint("user_id", "exam_id", "mode", name="in_progress_exam_user_id_exam_id_mode_key"),
    )
    op.create_index("in_progress_exam_user_id_saved_at_idx", "in_progress_exam", ["user_id", "saved_at"])

    # history.exam_id deliberately has NO ForeignKey: history survives exam
    # deletion, which is why nothing may join(Exam) on a history query.
    op.create_table(
        "history",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("user_id", sa.String(length=8), nullable=False),
        sa.Column("exam_id", sa.String(length=8), nullable=False),
        sa.Column("exam_title", sa.String(length=255), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("correct", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mode", sa.String(length=10), server_default="exam", nullable=True),
        sa.Column("taken_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="history_user_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="history_pkey"),
    )
    op.create_index("history_exam_id_idx", "history", ["exam_id"])
    op.create_index("history_user_id_taken_at_idx", "history", ["user_id", "taken_at"])


def downgrade() -> None:
    op.drop_table("history")
    op.drop_table("in_progress_exam")
    op.drop_table("question")
    op.drop_table("exam")
    op.drop_table("course")
    op.drop_table("user")
