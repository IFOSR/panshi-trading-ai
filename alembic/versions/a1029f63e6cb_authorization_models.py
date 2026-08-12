"""authorization_models

Revision ID: a1029f63e6cb
Revises: d251ce664501
"""

from alembic import op
import sqlalchemy as sa

revision = 'a1029f63e6cb'
down_revision = 'd251ce664501'


def upgrade() -> None:
    op.create_table('orders',
    sa.Column('order_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('strategy_id', sa.String(length=80), nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('pricing_type', sa.String(length=20), nullable=False),
    sa.Column('subscription_period', sa.String(length=20), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('refund_reason', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('order_id')
    )
    op.create_index('ix_orders_user_id', 'orders', ['user_id'], unique=False)
    op.create_table('user_entitlements',
    sa.Column('entitlement_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('strategy_id', sa.String(length=80), nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('access_type', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('order_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('entitlement_id')
    )
    op.create_index(
        'ix_user_entitlements_user_id',
        'user_entitlements', ['user_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_user_entitlements_user_id', table_name='user_entitlements')
    op.drop_table('user_entitlements')
    op.drop_index('ix_orders_user_id', table_name='orders')
    op.drop_table('orders')
