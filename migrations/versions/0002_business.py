"""Frozen PostgreSQL business schema."""

from pathlib import Path

from alembic import op

revision = "0002_business"
down_revision = "0001_bootstrap"
branch_labels = depends_on = None


def upgrade():
    sql = (Path(__file__).resolve().parents[1] / "sql/0002_business.sql").read_text()
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError("Destructive business downgrade requires a separately reviewed migration")
