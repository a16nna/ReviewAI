"""Initial schema: the original single-table design (findings stored as JSON on the review)."""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reviews",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("language", sa.String, nullable=False),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("is_mock", sa.Boolean, nullable=False),
        sa.Column("code_chars", sa.Integer, nullable=False),
        sa.Column("analyzers", sa.JSON, nullable=False),
        sa.Column("ai_error", sa.String, nullable=True),
        sa.Column("findings", sa.JSON, nullable=False),
    )
    op.create_index("ix_reviews_created_at", "reviews", ["created_at"])
    op.create_index("ix_reviews_language", "reviews", ["language"])


def downgrade():
    op.drop_table("reviews")
