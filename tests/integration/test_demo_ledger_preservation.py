"""Exercise reset on the disposable test DB, never on the actual durable ledger."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url

from aftercare.domain.contracts import BusinessError
from aftercare.llm.budget import BudgetLedger
from aftercare.repositories.models import ModelCall
from aftercare.services.demo import reset_demo


def test_demo_reset_refuses_existing_real_batch_ledger(service):
    conv = service.create_conversation("alice")
    call = BudgetLedger(service.sessions).reserve(
        "fake-real-no-transport",
        "offline-test",
        "sealed-real-batch",
        conv,
        "test",
        100,
        20,
        1000,
    )

    class DemoNamedTestSessions:
        kw = {
            "bind": SimpleNamespace(
                url=make_url(
                    "postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_demo"
                )
            )
        }

        def __call__(self):
            return service.sessions()

        def begin(self):
            return service.sessions.begin()

    with pytest.raises(BusinessError, match="REAL_LEDGER_RESET_FORBIDDEN"):
        reset_demo(DemoNamedTestSessions(), "demo-only")
    with service.sessions() as s:
        assert s.scalar(select(ModelCall.id)) == call
