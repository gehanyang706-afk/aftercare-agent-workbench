from concurrent.futures import ThreadPoolExecutor

import pytest

from aftercare.domain.contracts import BusinessError
from aftercare.llm.budget import BudgetLedger
from aftercare.repositories.models import Budget, ModelCall


def test_concurrent_reservations_do_not_overspend(service):
    conv = service.create_conversation("alice")
    ledger = BudgetLedger(service.sessions)

    def attempt(_):
        try:
            return ledger.reserve("p", "exact", "b", conv, "run", 60, 10, 100)
        except BusinessError as e:
            return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        out = list(pool.map(attempt, range(2)))
    assert sum(v == "BUDGET_EXHAUSTED" for v in out) == 1
    with service.sessions() as s:
        assert s.get(Budget, "p:exact:b").reserved == 70


def test_unknown_usage_retains_reservation_and_pauses(service):
    conv = service.create_conversation("alice")
    ledger = BudgetLedger(service.sessions)
    cid = ledger.reserve("p", "exact", "b", conv, "r", 20, 10, 100)
    ledger.settle(cid, None)
    with service.sessions() as s:
        budget = s.get(Budget, "p:exact:b")
        assert budget.reserved == 30 and budget.paused and budget.settled == 0
        assert s.get(ModelCall, cid).status == "USAGE_UNKNOWN"
    with pytest.raises(BusinessError, match="MODEL_BUDGET_PAUSED"):
        ledger.reserve("p", "exact", "b", conv, "r", 1, 1, 100)
    ledger.settle(cid, 17)
    with service.sessions() as s:
        assert s.get(Budget, "p:exact:b").reserved == 0
