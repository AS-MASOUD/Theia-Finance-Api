"""add is_active to assets

Revision ID: i3c4d5e6f7g8
Revises: h2b3c4d5e6f7
Create Date: 2026-10-01 20:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i3c4d5e6f7g8"
down_revision: str | None = "h2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.alter_column(
        "assets",
        "currency",
        type_=sa.String(length=10),
        existing_type=sa.String(length=3),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "assets",
        "currency",
        type_=sa.String(length=3),
        existing_type=sa.String(length=10),
        existing_nullable=False,
    )
    op.drop_column("assets", "is_active")
