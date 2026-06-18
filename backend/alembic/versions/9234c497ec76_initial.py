"""initial

Revision ID: 9234c497ec76
Revises:
Create Date: 2026-06-18 20:25:19.618514

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9234c497ec76"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("google_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_google_id"), "users", ["google_id"], unique=True)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    # Create urls table
    op.create_table(
        "urls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("short_id", sa.String(length=50), nullable=False),
        sa.Column("target_url", sa.String(), nullable=False),
        sa.Column("clicks_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password", sa.String(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_urls_short_id"), "urls", ["short_id"], unique=True)
    op.create_index(op.f("ix_urls_id"), "urls", ["id"], unique=False)

    # Create click_events table
    op.create_table(
        "click_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url_id", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=50), nullable=True),
        sa.Column("country", sa.String(length=50), nullable=True),
        sa.Column("city", sa.String(length=50), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("browser", sa.String(length=50), nullable=True),
        sa.Column("os", sa.String(length=50), nullable=True),
        sa.Column("device", sa.String(length=50), nullable=True),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_click_events_id"), "click_events", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_click_events_id"), table_name="click_events")
    op.drop_table("click_events")
    op.drop_index(op.f("ix_urls_id"), table_name="urls")
    op.drop_index(op.f("ix_urls_short_id"), table_name="urls")
    op.drop_table("urls")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_google_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
