from datetime import datetime, timedelta

from aftercare.domain.contracts import BusinessError


def require(condition: bool, code: str, message: str = ""):
    if not condition:
        raise BusinessError(code, message)


def check_window(
    action: str, status: str, delivered_at: datetime | None, now: datetime, rules: dict
):
    section = rules[action]
    require(status in section["allowed_order_states"], "INELIGIBLE_STATUS")
    if action != "cancel":
        require(delivered_at is not None, "MISSING_DELIVERY_TIME")
        require(
            timedelta(0) <= now - delivered_at <= timedelta(hours=section["window_hours"]),
            "OUTSIDE_POLICY_WINDOW",
        )
