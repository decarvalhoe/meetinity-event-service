"""Initial database schema for event service."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "202401010001"
down_revision = None
branch_labels = None
depends_on = None


def _timestamp_columns():
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            server_onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]


def upgrade() -> None:
    event_approval_status = sa.Enum(
        "pending", "approved", "rejected", name="event_approval_status"
    )
    bind = op.get_bind()
    event_approval_status.create(bind, checkfirst=True)

    op.create_table(
        "event_series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamp_columns(),
    )

    op.create_table(
        "event_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_duration_minutes", sa.Integer(), nullable=True),
        *_timestamp_columns(),
    )

    op.create_table(
        "event_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamp_columns(),
    )

    op.create_table(
        "event_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        *_timestamp_columns(),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=True),
        sa.Column("attendees", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("event_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("event_series.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint("attendees >= 0", name="ck_events_attendees_non_negative"),
    )

    op.create_table(
        "event_categories_events",
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("event_categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "event_tags_events",
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("event_tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "event_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamp_columns(),
        sa.UniqueConstraint("event_id", "locale", name="uq_event_translation_locale"),
    )

    op.create_table(
        "event_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", event_approval_status, nullable=False, server_default="pending"),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamp_columns(),
    )


def downgrade() -> None:
    op.drop_table("event_approvals")
    op.drop_table("event_translations")
    op.drop_table("event_tags_events")
    op.drop_table("event_categories_events")
    op.drop_table("events")
    op.drop_table("event_tags")
    op.drop_table("event_categories")
    op.drop_table("event_templates")
    op.drop_table("event_series")

    event_approval_status = sa.Enum(
        "pending", "approved", "rejected", name="event_approval_status"
    )
    event_approval_status.drop(op.get_bind(), checkfirst=True)
