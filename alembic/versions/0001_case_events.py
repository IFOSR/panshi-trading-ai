"""Initial case event tables.

Revision ID: 0001
"""

revision = "0001"
down_revision = None


def upgrade() -> None:
    from alembic import op
    import sqlalchemy as sa

    op.create_table(
        "cases",
        sa.Column("case_id", sa.String(36), primary_key=True),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "case_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_case_events_case_id", "case_events", ["case_id"])
    op.create_table(
        "analyses",
        sa.Column("analysis_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_analyses_case_id", "analyses", ["case_id"])
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("command", sa.String(40), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.UniqueConstraint("case_id", "command", "key"),
    )


def downgrade() -> None:
    from alembic import op

    op.drop_table("idempotency_keys")
    op.drop_index("ix_analyses_case_id", table_name="analyses")
    op.drop_table("analyses")
    op.drop_index("ix_case_events_case_id", table_name="case_events")
    op.drop_table("case_events")
    op.drop_table("cases")
