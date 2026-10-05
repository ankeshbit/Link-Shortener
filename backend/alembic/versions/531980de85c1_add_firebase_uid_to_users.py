"""add firebase_uid to users

Revision ID: 531980de85c1
Revises: 9234c497ec76
Create Date: 2026-10-05 15:21:39.899986

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '531980de85c1'
down_revision = '9234c497ec76'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("firebase_uid", sa.String(length=128), nullable=True))
    op.create_index(op.f("ix_users_firebase_uid"), "users", ["firebase_uid"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_firebase_uid"), table_name="users")
    op.drop_column("users", "firebase_uid")
