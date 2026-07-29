"""Add event ordering and owned idempotency claims.

Revision ID: 0002
Revises: 0001
"""

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    import json

    from alembic import op
    import sqlalchemy as sa

    with op.batch_alter_table("cases") as batch:
        batch.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="0")
        )
    with op.batch_alter_table("case_events") as batch:
        batch.add_column(sa.Column("sequence", sa.Integer(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT event_id, case_id FROM case_events "
            "ORDER BY case_id, created_at, event_id"
        )
    ).fetchall()
    sequences: dict[str, int] = {}
    for event_id, case_id in rows:
        sequences[case_id] = sequences.get(case_id, 0) + 1
        connection.execute(
            sa.text("UPDATE case_events SET sequence = :sequence WHERE event_id = :event_id"),
            {"sequence": sequences[case_id], "event_id": event_id},
        )
    for case_id, version in sequences.items():
        connection.execute(
            sa.text("UPDATE cases SET version = :version WHERE case_id = :case_id"),
            {"version": version, "case_id": case_id},
        )

    with op.batch_alter_table("case_events") as batch:
        batch.alter_column("sequence", nullable=False)
        batch.create_unique_constraint(
            "uq_case_events_case_sequence",
            ["case_id", "sequence"],
        )
    with op.batch_alter_table("idempotency_keys") as batch:
        batch.add_column(
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="COMPLETED",
            )
        )
        batch.add_column(
            sa.Column(
                "owner_id",
                sa.String(36),
                nullable=False,
                server_default="legacy",
            )
        )
        batch.alter_column("result", nullable=True)
    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("sequence", sa.Integer(), nullable=True))

    analysis_events = connection.execute(
        sa.text(
            "SELECT case_id, payload, sequence FROM case_events "
            "WHERE event_type = 'ANALYSIS_COMPLETED' ORDER BY case_id, sequence"
        )
    ).fetchall()
    for case_id, payload, sequence in analysis_events:
        if isinstance(payload, str):
            payload = json.loads(payload)
        connection.execute(
            sa.text(
                "UPDATE analyses SET sequence = :sequence "
                "WHERE case_id = :case_id AND analysis_id = :analysis_id"
            ),
            {
                "sequence": sequence,
                "case_id": case_id,
                "analysis_id": payload["analysis_id"],
            },
        )
    with op.batch_alter_table("analyses") as batch:
        batch.alter_column("sequence", nullable=False)
        batch.create_unique_constraint(
            "uq_analyses_case_sequence",
            ["case_id", "sequence"],
        )


def downgrade() -> None:
    from alembic import op

    with op.batch_alter_table("analyses") as batch:
        batch.drop_constraint("uq_analyses_case_sequence", type_="unique")
        batch.drop_column("sequence")
    with op.batch_alter_table("idempotency_keys") as batch:
        batch.alter_column("result", nullable=False)
        batch.drop_column("owner_id")
        batch.drop_column("status")
    with op.batch_alter_table("case_events") as batch:
        batch.drop_constraint("uq_case_events_case_sequence", type_="unique")
        batch.drop_column("sequence")
    with op.batch_alter_table("cases") as batch:
        batch.drop_column("version")
