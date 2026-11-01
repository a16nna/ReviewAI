"""Store verified evidence (the quoted offending code line) with each finding."""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("findings") as b:
        b.add_column(sa.Column("evidence", sa.Text, nullable=True))


def downgrade():
    with op.batch_alter_table("findings") as b:
        b.drop_column("evidence")
