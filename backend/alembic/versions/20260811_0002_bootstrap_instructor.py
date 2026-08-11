"""bootstrap instructor account

Kept separate from the schema baseline on purpose: `alembic upgrade 0001 --sql`
then needs no environment at all, so pure DDL can be rendered and diffed against
the models without a database.

This account is load-bearing. `POST /api/auth/register` always creates students
and no route promotes anyone, so without this seed `/api/admin/dashboard` is
permanently 403 and no content is ever shared.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-11
"""

import os
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BOOTSTRAP_ID = "bootstrp"  # fixed 8-char id so later revisions need no lookup


def upgrade() -> None:
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL")
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        raise SystemExit(
            "BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD must be set to run migration 0002. "
            "They create the first instructor account. Set them in .env, run the migration, then "
            "change the password in the app."
        )
    if len(password.encode("utf-8")) > 72:
        raise SystemExit("BOOTSTRAP_ADMIN_PASSWORD must be at most 72 bytes (bcrypt's limit)")

    import bcrypt

    users = sa.table(
        "user",
        sa.column("id", sa.String),
        sa.column("email", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("role", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    op.bulk_insert(
        users,
        [
            {
                "id": BOOTSTRAP_ID,
                "email": email.strip().lower(),
                "password_hash": bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8"),
                "role": "instructor",
                "created_at": datetime.now(),
            }
        ],
    )


def downgrade() -> None:
    op.execute(sa.text(f"DELETE FROM \"user\" WHERE id = '{BOOTSTRAP_ID}'"))
