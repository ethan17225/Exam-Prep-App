"""admin role and audit log

Two things, both needed before the platform surface can work at all:

1. The `admin_audit_log` table. Append-only, and the only account of who changed
   a role, reset a password or deleted somebody's work.
2. Promotes the bootstrap account from `instructor` to `admin`. Revision 0002
   created it as an instructor because that was the highest role at the time, and
   nothing else can mint an admin — `POST /api/auth/register` rejects the role and
   the admin-only create route needs an admin to call it. Without this step a
   fresh deployment has no way to reach `/api/platform/*` at all.

`user.role` needs no DDL: it is a plain String(10) with no CHECK constraint, and
'admin' is five characters. That was a deliberate choice in the baseline — a
native Postgres ENUM would have needed an ALTER TYPE here, which cannot run
inside a transaction and which autogenerate does not model.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.identifiers import ID_LENGTH

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fixed by revision 0002 so no lookup is needed here either.
BOOTSTRAP_ID = "bootstrp"


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        # SET NULL, not CASCADE: deleting an admin must not erase the record of
        # what they did, which is why actor_email is stored alongside.
        sa.Column("actor_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        # No FK on target_id on purpose: the point of several of these rows is
        # that the target no longer exists.
        sa.Column("target_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("target_label", sa.String(length=255), nullable=False),
        sa.Column(
            "detail",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["user.id"], name="admin_audit_log_actor_id_fkey", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="admin_audit_log_pkey"),
    )
    # Named to match POSTGRES_INDEXES_NAMING_CONVENTION's "ix" rule, so
    # autogenerate does not propose churning it on the next revision.
    op.create_index("admin_audit_log_created_at_idx", "admin_audit_log", ["created_at"])

    # Promote the bootstrap account. Guarded on the current role so re-running a
    # stamped-then-upgraded database cannot demote a deployment that has since
    # moved its admin elsewhere, and so it silently no-ops where 0002 never ran.
    op.execute(
        sa.text(
            f"""
            UPDATE "user"
            SET role = 'admin', instructor_id = NULL
            WHERE id = '{BOOTSTRAP_ID}' AND role = 'instructor'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE "user"
            SET role = 'instructor'
            WHERE id = '{BOOTSTRAP_ID}' AND role = 'admin'
            """
        )
    )
    op.drop_index("admin_audit_log_created_at_idx", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
