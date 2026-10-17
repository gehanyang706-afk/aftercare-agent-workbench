"""Transactional offline/real-model budget ledger."""

from alembic import op

revision = "0004_budget"
down_revision = "0003_retrieval"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE budgets (id VARCHAR PRIMARY KEY, cap BIGINT NOT NULL,
        settled BIGINT NOT NULL, reserved BIGINT NOT NULL, paused BOOLEAN NOT NULL,
        CHECK (cap >= 0 AND settled >= 0 AND reserved >= 0))""")
    op.execute("""CREATE TABLE model_calls (id VARCHAR PRIMARY KEY,
        budget_id VARCHAR NOT NULL REFERENCES budgets(id), provider VARCHAR NOT NULL,
        exact_model VARCHAR NOT NULL, batch_id VARCHAR NOT NULL,
        conversation_id VARCHAR NOT NULL REFERENCES conversations(id), run_id VARCHAR NOT NULL,
        reserved INTEGER NOT NULL, usage INTEGER, status VARCHAR NOT NULL,
        request_id VARCHAR, details JSON NOT NULL, created_at TIMESTAMPTZ NOT NULL)""")
    for name in ["budget_id", "conversation_id", "run_id"]:
        op.execute(f"CREATE INDEX ix_model_calls_{name} ON model_calls({name})")


def downgrade():
    op.execute("DROP TABLE model_calls")
    op.execute("DROP TABLE budgets")
