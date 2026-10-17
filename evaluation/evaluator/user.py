"""Evaluator-side adaptive users. Their goal is never sent to the product actor."""

from typing import Protocol

from aftercare.llm.gateway import RealModelCallsDisabled


class UserPolicy(Protocol):
    def accepts(self, preview_payload: dict) -> bool: ...


class ScriptedUser:
    def __init__(self, goal):
        self.goal = goal

    def accepts(self, preview_payload):
        return self.goal.get("accept", True) and all(
            preview_payload.get(key) == self.goal[key]
            for key in ("order_id", "action", "target_variant", "quantity")
            if key in self.goal
        )


class ModelUser:
    """Optional interface only. No implicit user-simulator API costs in offline stages."""

    def accepts(self, preview_payload):
        raise RealModelCallsDisabled("MODEL_USER_REQUIRES_SEPARATE_PHASE_6_BATCH_APPROVAL")
