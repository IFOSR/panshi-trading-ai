"""Add a database timestamp for atomic idempotency lease takeover.

Revision ID: 0003
Revises: 0002
"""

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    from alembic import op
    import sqlalchemy as sa

    with op.batch_alter_table("idempotency_keys") as batch:
        batch.add_column(
            sa.Column(
                "claimed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )


def downgrade() -> None:
    from alembic import op

    with op.batch_alter_table("idempotency_keys") as batch:
        batch.drop_column("claimed_at")
