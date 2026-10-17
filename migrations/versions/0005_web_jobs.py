"""Server-owned identities and leased jobs."""

from alembic import op

revision = "0005_web_jobs"
down_revision = "0004_budget"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE demo_sessions(token_hash VARCHAR PRIMARY KEY,
        customer_id VARCHAR NOT NULL REFERENCES customers(id), csrf_token VARCHAR NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL)""")
    op.execute("""CREATE TABLE jobs(id VARCHAR PRIMARY KEY,
        conversation_id VARCHAR NOT NULL REFERENCES conversations(id),
        message_id VARCHAR REFERENCES messages(id), dedup_key VARCHAR NOT NULL UNIQUE,
        kind VARCHAR NOT NULL, revision INTEGER NOT NULL, status VARCHAR NOT NULL,
        lease_owner VARCHAR, lease_expires_at TIMESTAMPTZ, attempt INTEGER NOT NULL,
        cancel_requested BOOLEAN NOT NULL, result JSON NOT NULL,
        created_at TIMESTAMPTZ NOT NULL)""")
    op.execute("CREATE INDEX ix_jobs_conversation_id ON jobs(conversation_id)")


def downgrade():
    op.execute("DROP TABLE jobs")
    op.execute("DROP TABLE demo_sessions")
