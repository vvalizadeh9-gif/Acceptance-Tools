"""action center schema: province table, DT/depreciation fields, per-village
acceptance restructure, monthly snapshots

Revision ID: a1b2c3d4e5f6
Revises: d383bcacc911
Create Date: 2026-07-03

Adds the data model behind the role-specific action centers:

  * province            — 31-row reference table; the single backbone every
                          geographic scope/breakdown joins through (Regional
                          Manager, PSO Coordinator, and CRA Region are three
                          independent partitions, only province is common).
  * work_item           — +dt_status, +dt_problematic_category,
                          +dt_subcontractor_name, +depreciation_status.
  * village_acceptance  — RESTRUCTURED from one-row-per-technology to one wide
                          row per (site, village): 2G/3G/4G ICT and CRA
                          statuses, cached Final flags, comment, letter fields,
                          approved_by/at, and village-grain depreciation.
  * monthly_metric_snapshot — month-start baselines for "+/- vs last month".

NOTE on the village_acceptance restructure: the per-technology -> per-village
change cannot be reconciled row-by-row on existing data, and the only source
of acceptance rows so far is the (re-runnable) CPM import, so this migration
clears village_acceptance (and its letter_village_mapping links) before
reshaping. Re-run the CPM import afterwards to repopulate.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd383bcacc911'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. Province reference table ---------------------------------------
    op.create_table(
        'province',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('cra_region', sa.String(length=50), nullable=False),
        sa.Column('operational_region_name', sa.String(length=100), nullable=True),
        sa.Column('regional_manager_id', sa.Uuid(), nullable=True),
        sa.Column('pso_coordinator_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['regional_manager_id'], ['app_user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['pso_coordinator_id'], ['app_user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_province_name'),
    )

    # --- 2. Work Item: DT + depreciation fields (site grain) --------------
    # Plain add_column of nullable columns is portable across SQLite/Postgres.
    op.add_column('work_item', sa.Column('dt_status', sa.String(length=20), nullable=True))
    op.add_column('work_item', sa.Column('dt_problematic_category', sa.String(length=30), nullable=True))
    op.add_column('work_item', sa.Column('dt_subcontractor_name', sa.String(length=255), nullable=True))
    op.add_column('work_item', sa.Column('depreciation_status', sa.String(length=30), nullable=True))

    # --- 3. Village Acceptance: per-technology -> per-village --------------
    # Clear existing rows (only the re-runnable CPM import populates these)
    # and their letter links, so the grain change is clean.
    op.execute('DELETE FROM letter_village_mapping')
    op.execute('DELETE FROM village_acceptance')

    with op.batch_alter_table('village_acceptance', schema=None) as batch_op:
        # Old per-tech shape
        batch_op.drop_constraint('uq_acceptance_composite_key', type_='unique')
        batch_op.drop_column('technology')
        batch_op.drop_column('ict_status')
        batch_op.drop_column('cra_status')
        # ICT
        batch_op.add_column(sa.Column('ict_2g', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('ict_3g', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('ict_4g', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('ict_final', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('ict_comment', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('ict_letter_number', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('ict_letter_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('ict_approved_by', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('ict_approved_at', sa.DateTime(timezone=True), nullable=True))
        # CRA
        batch_op.add_column(sa.Column('cra_2g', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('cra_3g', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('cra_4g', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('cra_final', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('cra_comment', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('cra_letter_number', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('cra_letter_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('cra_approved_by', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('cra_approved_at', sa.DateTime(timezone=True), nullable=True))
        # Village-grain depreciation
        batch_op.add_column(sa.Column('depreciation_status', sa.String(length=30), nullable=True))
        # New grain + FKs
        batch_op.create_unique_constraint('uq_acceptance_site_village', ['site_id', 'village_id'])
        batch_op.create_foreign_key('fk_acceptance_ict_approved_by', 'app_user', ['ict_approved_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_acceptance_cra_approved_by', 'app_user', ['cra_approved_by'], ['id'], ondelete='SET NULL')

    # --- 4. Monthly metric snapshots --------------------------------------
    op.create_table(
        'monthly_metric_snapshot',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('scope_type', sa.String(length=30), nullable=False),
        sa.Column('scope_key', sa.String(length=120), server_default=sa.text("''"), nullable=False),
        sa.Column('metric', sa.String(length=40), nullable=False),
        sa.Column('value', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('period', 'scope_type', 'scope_key', 'metric', name='uq_snapshot_period_scope_metric'),
    )


def downgrade() -> None:
    op.drop_table('monthly_metric_snapshot')

    op.execute('DELETE FROM letter_village_mapping')
    op.execute('DELETE FROM village_acceptance')

    with op.batch_alter_table('village_acceptance', schema=None) as batch_op:
        batch_op.drop_constraint('fk_acceptance_cra_approved_by', type_='foreignkey')
        batch_op.drop_constraint('fk_acceptance_ict_approved_by', type_='foreignkey')
        batch_op.drop_constraint('uq_acceptance_site_village', type_='unique')
        for col in (
            'depreciation_status',
            'cra_approved_at', 'cra_approved_by', 'cra_letter_date', 'cra_letter_number',
            'cra_comment', 'cra_final', 'cra_4g', 'cra_3g', 'cra_2g',
            'ict_approved_at', 'ict_approved_by', 'ict_letter_date', 'ict_letter_number',
            'ict_comment', 'ict_final', 'ict_4g', 'ict_3g', 'ict_2g',
        ):
            batch_op.drop_column(col)
        batch_op.add_column(sa.Column('technology', sa.String(length=20), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('ict_status', sa.String(length=20), nullable=False, server_default='not_submitted'))
        batch_op.add_column(sa.Column('cra_status', sa.String(length=20), nullable=False, server_default='not_submitted'))
        batch_op.create_unique_constraint('uq_acceptance_composite_key', ['site_id', 'village_id', 'technology'])

    op.drop_column('work_item', 'depreciation_status')
    op.drop_column('work_item', 'dt_subcontractor_name')
    op.drop_column('work_item', 'dt_problematic_category')
    op.drop_column('work_item', 'dt_status')

    op.drop_table('province')
