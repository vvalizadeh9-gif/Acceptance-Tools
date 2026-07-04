"""add work_item.dt_date (drive-test delivery date)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-04

The CPM "DT Date" column: when the drive test was delivered/completed. Needed
for the Project Delivery dashboard's monthly/yearly delivery charts. Nullable,
so this is a plain add_column safe on both SQLite and Postgres.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('work_item', sa.Column('dt_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('work_item', 'dt_date')
