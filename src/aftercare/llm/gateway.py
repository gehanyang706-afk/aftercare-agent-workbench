from aftercare.config import Settings


class RealModelCallsDisabled(RuntimeError):
    pass


def create_real_client(settings: Settings) -> None:
    # A flag alone is never authorization. Phase 3 adds the ledger; phase 6 adds approval.
    raise RealModelCallsDisabled("REAL_MODEL_CALLS_DISABLED_PHASES_0_TO_5")
