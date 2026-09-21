"""drop Question.number; key attempts by Question.id

Answers, flagged, and question_order on open attempts were keyed by the
per-exam `number` column. Remap those JSONB values to `Question.id` before
dropping the column, and rewrite history blobs so `question_id` is identity
and `question_number` is the 1-based display index of that attempt.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Open attempts: JSONB keys and arrays were question.number; they become
    # question.id. Unmatched entries (question already deleted) are dropped.
    op.execute(
        sa.text(
            """
            UPDATE in_progress_exam p
            SET
                answers = COALESCE((
                    SELECT jsonb_object_agg(q.id::text, kv.value)
                    FROM jsonb_each(COALESCE(p.answers, '{}'::jsonb)) AS kv(key, value)
                    JOIN question q
                      ON q.exam_id = p.exam_id
                     AND kv.key ~ '^[0-9]+$'
                     AND q.number = (kv.key)::int
                ), '{}'::jsonb),
                flagged = COALESCE((
                    SELECT jsonb_agg(q.id ORDER BY e.ordinality)
                    FROM jsonb_array_elements(COALESCE(p.flagged, '[]'::jsonb))
                         WITH ORDINALITY AS e(val, ordinality)
                    JOIN question q
                      ON q.exam_id = p.exam_id
                     AND q.number = (e.val #>> '{}')::int
                ), '[]'::jsonb),
                question_order = COALESCE((
                    SELECT jsonb_agg(q.id ORDER BY e.ordinality)
                    FROM jsonb_array_elements(COALESCE(p.question_order, '[]'::jsonb))
                         WITH ORDINALITY AS e(val, ordinality)
                    JOIN question q
                      ON q.exam_id = p.exam_id
                     AND q.number = (e.val #>> '{}')::int
                ), '[]'::jsonb)
            """
        )
    )

    # History is a snapshot: keep a display index (1-based position in this
    # attempt) under question_number, and store the stable Question.id beside it.
    op.execute(
        sa.text(
            """
            UPDATE history h
            SET results = COALESCE((
                SELECT jsonb_agg(
                    (e.elem - 'question_number')
                    || jsonb_build_object(
                        'question_id', COALESCE(
                            (
                                SELECT q.id FROM question q
                                WHERE q.exam_id = h.exam_id
                                  AND e.elem->>'question_number' ~ '^[0-9]+$'
                                  AND q.number = (e.elem->>'question_number')::int
                                LIMIT 1
                            ),
                            NULLIF(e.elem->>'question_number', '')::int
                        ),
                        'question_number', e.ordinality
                    )
                    ORDER BY e.ordinality
                )
                FROM jsonb_array_elements(COALESCE(h.results, '[]'::jsonb))
                     WITH ORDINALITY AS e(elem, ordinality)
            ), '[]'::jsonb)
            """
        )
    )

    op.drop_column("question", "number")


def downgrade() -> None:
    op.add_column("question", sa.Column("number", sa.Integer(), nullable=True))
    # Insertion order is the only remaining sequence after the drop.
    op.execute(
        sa.text(
            """
            UPDATE question q
            SET number = sub.n
            FROM (
                SELECT id, row_number() OVER (PARTITION BY exam_id ORDER BY id) AS n
                FROM question
            ) sub
            WHERE q.id = sub.id
            """
        )
    )
    op.alter_column("question", "number", nullable=False)
    # JSONB attempt keys stay as question.id — a reverse remap would need the
    # original numbers, which this downgrade cannot recover.
