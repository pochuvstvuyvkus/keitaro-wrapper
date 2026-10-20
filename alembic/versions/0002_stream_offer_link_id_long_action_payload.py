"""stream offer link id, long action payload

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20 18:19:30.980703
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stream_offers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kt_link_id", sa.Integer(), nullable=True))

    with op.batch_alter_table("streams", schema=None) as batch_op:
        batch_op.alter_column(
            "action_payload",
            existing_type=sa.VARCHAR(length=2048),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("streams", schema=None) as batch_op:
        batch_op.alter_column(
            "action_payload",
            existing_type=sa.Text(),
            type_=sa.VARCHAR(length=2048),
            existing_nullable=True,
        )

    with op.batch_alter_table("stream_offers", schema=None) as batch_op:
        batch_op.drop_column("kt_link_id")
