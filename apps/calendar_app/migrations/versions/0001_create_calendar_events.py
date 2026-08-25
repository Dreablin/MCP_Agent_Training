from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_calendar_events"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("start_at", sa.String(length=40), nullable=False),
        sa.Column("end_at", sa.String(length=40), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("location", sa.String(length=300), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calendar_events_status", "calendar_events", ["status"])
    op.create_index("ix_calendar_events_start_at", "calendar_events", ["start_at"])
    op.create_index("ix_calendar_events_end_at", "calendar_events", ["end_at"])


def downgrade() -> None:
    op.drop_index("ix_calendar_events_end_at", table_name="calendar_events")
    op.drop_index("ix_calendar_events_start_at", table_name="calendar_events")
    op.drop_index("ix_calendar_events_status", table_name="calendar_events")
    op.drop_table("calendar_events")
