"""Add isolated benchmark accounting; preserve all existing ledger rows."""

from alembic import op

from aftercare.repositories.models import (
    ActorBudget,
    ExperimentCall,
    ExperimentEpisode,
    ExperimentRun,
    SharedModelQuota,
)

revision = "0006_experiments"
down_revision = "0005_web_jobs"
branch_labels = depends_on = None


def upgrade():
    for model in (ExperimentRun, SharedModelQuota, ExperimentEpisode, ActorBudget, ExperimentCall):
        model.__table__.create(op.get_bind())


def downgrade():
    raise RuntimeError("EXPERIMENT_LEDGER_DOWNGRADE_FORBIDDEN")
