"""split app_user name into first/last + add phone

Revision ID: e4f5a6b7c8d9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-05

Task 9 (Admin / User Management rebuild):

  * app_user.first_name, app_user.last_name — the name is now stored split,
    which is what the Admin edits and what the users table shows in two
    columns. Both nullable so the add is safe on a populated table.

  * app_user.phone — optional contact number, nullable.

  * full_name is KEPT (non-null, unchanged): it stays the composed
    "first last" display string so every existing read of full_name
    (contractor lists, province RM/coordinator labels, the sidebar) keeps
    working with no code change. The API composes it on write.

Backfill: split each existing full_name on the FIRST space — everything
before it becomes first_name, the remainder becomes last_name. Single-word
names land entirely in first_name with an empty last_name. Done with plain
SQL so it runs identically on Postgres (prod) and SQLite (local dev).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('app_user', sa.Column('first_name', sa.String(length=120), nullable=True))
    op.add_column('app_user', sa.Column('last_name', sa.String(length=120), nullable=True))
    op.add_column('app_user', sa.Column('phone', sa.String(length=40), nullable=True))

    # Backfill first/last from the existing full_name. Split on the first
    # space; portable across Postgres and SQLite.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, full_name FROM app_user")).fetchall()
    for row in rows:
        name = (row.full_name or "").strip()
        if " " in name:
            first, last = name.split(" ", 1)
        else:
            first, last = name, ""
        bind.execute(
            sa.text("UPDATE app_user SET first_name = :f, last_name = :l WHERE id = :id"),
            {"f": first, "l": last, "id": row.id},
        )


def downgrade() -> None:
    op.drop_column('app_user', 'phone')
    op.drop_column('app_user', 'last_name')
    op.drop_column('app_user', 'first_name')
