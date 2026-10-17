"""Exact pgvector policy index."""

from alembic import op

revision = "0003_retrieval"
down_revision = "0002_business"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE policy_chunks (
        id VARCHAR PRIMARY KEY, corpus_hash VARCHAR NOT NULL, model_revision VARCHAR NOT NULL,
        metadata_json JSON NOT NULL, embedding vector(512))""")


def downgrade():
    op.execute("DROP TABLE policy_chunks")
