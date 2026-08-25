from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_email_messages"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sender_name", sa.String(length=200), nullable=False),
        sa.Column("sender_email", sa.String(length=320), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("received_at", sa.String(length=40), nullable=False),
        sa.Column("folder", sa.String(length=20), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_messages_folder", "email_messages", ["folder"])
    op.create_index("ix_email_messages_is_read", "email_messages", ["is_read"])
    op.create_index("ix_email_messages_received_at", "email_messages", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_email_messages_received_at", table_name="email_messages")
    op.drop_index("ix_email_messages_is_read", table_name="email_messages")
    op.drop_index("ix_email_messages_folder", table_name="email_messages")
    op.drop_table("email_messages")
