"""user profiles, per-instructor invite codes, per-exam pass grade

Every NOT NULL column added here follows the three-step rule: add nullable,
backfill, SET NOT NULL, then drop the server_default used to get there. A
lingering default on `pass_grade` would turn "forgot to set the pass grade" from
a loud error into a silent 72.

`display_name` stays nullable — it is the "not onboarded yet" signal the frontend
reads — but existing accounts are backfilled from the email local part so nobody
who already has data is forced through onboarding.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.auth.models import DISPLAY_NAME_MAX
from src.grading.constants import DEFAULT_PASS_GRADE
from src.identifiers import ID_LENGTH

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── user profile ──────────────────────────────────────────────
    op.add_column("user", sa.Column("display_name", sa.String(length=DISPLAY_NAME_MAX), nullable=True))
    op.add_column("user", sa.Column("avatar", sa.Text(), nullable=True))
    op.add_column("user", sa.Column("invite_code", sa.String(length=ID_LENGTH), nullable=True))
    op.add_column("user", sa.Column("instructor_id", sa.String(length=ID_LENGTH), nullable=True))
    op.create_foreign_key("user_instructor_id_fkey", "user", "user", ["instructor_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint("user_invite_code_key", "user", ["invite_code"])
    op.create_index("user_instructor_id_idx", "user", ["instructor_id"])

    # Existing accounts predate onboarding and already own content, so they get a
    # name rather than being bounced to the onboarding page on next sign-in.
    op.execute(
        sa.text(
            """
            UPDATE "user"
            SET display_name = left(split_part(email, '@', 1), :max_len)
            WHERE display_name IS NULL
            """
        ).bindparams(max_len=DISPLAY_NAME_MAX)
    )

    # Every instructor needs a personal code: it is the only way a student can
    # register and be linked, so an instructor without one cannot enrol anybody.
    # Derived from the id rather than generated in Python so this stays pure DDL
    # plus DML — `alembic upgrade head --sql` must render with no database. md5 of
    # a unique id is unique, and 12 hex chars is the `new_id()` format.
    op.execute(
        sa.text(
            f"""
            UPDATE "user"
            SET invite_code = substr(md5(id), 1, {ID_LENGTH})
            WHERE role = 'instructor' AND invite_code IS NULL
            """
        )
    )

    # ── per-exam pass grade ───────────────────────────────────────
    # Nullable first, then backfilled with the threshold every existing attempt
    # was actually graded against, then locked down.
    for table in ("exam", "history"):
        op.add_column(table, sa.Column("pass_grade", sa.Integer(), nullable=True))
        op.execute(
            sa.text(f"UPDATE {table} SET pass_grade = :grade WHERE pass_grade IS NULL").bindparams(
                grade=DEFAULT_PASS_GRADE
            )
        )
        op.alter_column(table, "pass_grade", nullable=False)


def downgrade() -> None:
    op.drop_column("history", "pass_grade")
    op.drop_column("exam", "pass_grade")

    op.drop_index("user_instructor_id_idx", table_name="user")
    op.drop_constraint("user_invite_code_key", "user", type_="unique")
    op.drop_constraint("user_instructor_id_fkey", "user", type_="foreignkey")
    op.drop_column("user", "instructor_id")
    op.drop_column("user", "invite_code")
    op.drop_column("user", "avatar")
    op.drop_column("user", "display_name")
