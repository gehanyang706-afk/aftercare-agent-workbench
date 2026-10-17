"""Install vector extension; business tables are introduced in phase 1."""

from alembic import op

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Extension lifecycle belongs to the database, not to application rollback.
    # Retaining it avoids destroying future policy embeddings.
    pass
