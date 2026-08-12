"""strategy_store_models

Revision ID: d251ce664501
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa

revision = 'd251ce664501'
down_revision = '0004'


def upgrade() -> None:
    op.create_table('strategies',
    sa.Column('strategy_id', sa.String(length=80), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=40), nullable=True),
    sa.Column('supported_markets', sa.JSON(), nullable=False),
    sa.Column('supported_timeframes', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('entrypoint', sa.String(length=240), nullable=False),
    sa.Column('input_schema_version', sa.String(length=40), nullable=False),
    sa.Column('output_schema_version', sa.String(length=40), nullable=False),
    sa.Column('risk_profile_id', sa.String(length=120), nullable=True),
    sa.Column('process_label', sa.String(length=120), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('strategy_id')
    )
    op.create_table('strategy_performance_signals',
    sa.Column('signal_id', sa.String(length=36), nullable=False),
    sa.Column('strategy_id', sa.String(length=80), nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('contract', sa.String(length=80), nullable=False),
    sa.Column('signal_date', sa.Date(), nullable=False),
    sa.Column('direction', sa.String(length=20), nullable=False),
    sa.Column('entry_price', sa.Float(), nullable=True),
    sa.Column('exit_price', sa.Float(), nullable=True),
    sa.Column('return_pct', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('closed_date', sa.Date(), nullable=True),
    sa.Column('evidence', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('signal_id')
    )
    op.create_index(
        'ix_strategy_performance_signals_strategy_id',
        'strategy_performance_signals', ['strategy_id'], unique=False,
    )
    op.create_table('strategy_performance_summaries',
    sa.Column('summary_id', sa.String(length=120), nullable=False),
    sa.Column('strategy_id', sa.String(length=80), nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('period', sa.String(length=20), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('total_return', sa.Float(), nullable=True),
    sa.Column('annualized_return', sa.Float(), nullable=True),
    sa.Column('max_drawdown', sa.Float(), nullable=True),
    sa.Column('signal_count', sa.Integer(), nullable=False),
    sa.Column('win_count', sa.Integer(), nullable=False),
    sa.Column('loss_count', sa.Integer(), nullable=False),
    sa.Column('win_rate', sa.Float(), nullable=True),
    sa.Column('avg_win', sa.Float(), nullable=True),
    sa.Column('avg_loss', sa.Float(), nullable=True),
    sa.Column('equity_curve', sa.JSON(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('summary_id')
    )
    op.create_index(
        'ix_strategy_performance_summaries_strategy_id',
        'strategy_performance_summaries', ['strategy_id'], unique=False,
    )
    op.create_table('strategy_versions',
    sa.Column('version_id', sa.String(length=120), nullable=False),
    sa.Column('strategy_id', sa.String(length=80), nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('manifest', sa.JSON(), nullable=False),
    sa.Column('pricing_type', sa.String(length=20), nullable=False),
    sa.Column('monthly_price', sa.Integer(), nullable=True),
    sa.Column('yearly_price', sa.Integer(), nullable=True),
    sa.Column('lifetime_price', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(
        ['strategy_id'], ['strategies.strategy_id'], ondelete='CASCADE',
    ),
    sa.PrimaryKeyConstraint('version_id')
    )
    op.create_index(
        'ix_strategy_versions_strategy_id',
        'strategy_versions', ['strategy_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_strategy_versions_strategy_id', table_name='strategy_versions')
    op.drop_table('strategy_versions')
    op.drop_index(
        'ix_strategy_performance_summaries_strategy_id',
        table_name='strategy_performance_summaries',
    )
    op.drop_table('strategy_performance_summaries')
    op.drop_index(
        'ix_strategy_performance_signals_strategy_id',
        table_name='strategy_performance_signals',
    )
    op.drop_table('strategy_performance_signals')
    op.drop_table('strategies')
