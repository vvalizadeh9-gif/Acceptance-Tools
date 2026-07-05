"""add Finance role + work_item.official_assignment_date (تاریخ ابلاغ)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-05

Slice 1 (foundation) of the operational build:

  * work_item.official_assignment_date — the date MTN officially assigned/
    announced the site (تاریخ ابلاغ). Distinct from the DT-subcontractor
    assignment (ContractorAssignment). Nullable, no workflow use today;
    it exists for the future Budget/depreciation module. Plain add_column,
    safe on both dialects.

  * Widen the app_user role CHECK constraint to admit 'finance' (7th role).
    On Postgres this is a drop+recreate of chk_user_role_vocab. On SQLite
    (local dev only) a CHECK can't be dropped in place, so we recreate the
    constraint via batch mode. Existing rows all hold one of the original
    six values, so widening the allowed set never violates anything.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLES_6 = "('admin','project_manager','dt_coordinator','field_subcontractor','regional_manager','viewer')"
_ROLES_7 = "('admin','project_manager','dt_coordinator','field_subcontractor','regional_manager','finance','viewer')"


def _set_role_constraint(values_sql: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite can't ALTER a CHECK in place — recreate via batch.
        with op.batch_alter_table("app_user") as batch:
            batch.drop_constraint("chk_user_role_vocab", type_="check")
            batch.create_check_constraint("chk_user_role_vocab", f"role IN {values_sql}")
    else:
        op.drop_constraint("chk_user_role_vocab", "app_user", type_="check")
        op.create_check_constraint("chk_user_role_vocab", "app_user", f"role IN {values_sql}")


def upgrade() -> None:
    op.add_column('work_item', sa.Column('official_assignment_date', sa.Date(), nullable=True))
    _set_role_constraint(_ROLES_7)


def downgrade() -> None:
    _set_role_constraint(_ROLES_6)
    op.drop_column('work_item', 'official_assignment_date')
