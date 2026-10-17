"""Public scenario schema. Hidden evaluator fields must never enter model context."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    family_id: str
    category: Literal["basic", "revision", "boundary", "recovery"]
    split: Literal["dev", "holdout"]
    seed: int
    clock: datetime
    fixture_reference: str = "demo-v1"
    fixture_changes: list[dict] = Field(default_factory=list)
    initial_user_message: str
    hidden_user_goal: dict
    user_known_facts: dict = Field(default_factory=dict)
    # steps: {on: clarification|preview|after_commit, say?: text, decision?: accept|reject}
    user_behavior_policy: list[dict] = Field(default_factory=list)
    public_policy_manifest: str = "data/policies/manifest.json"
    # Supported fault kinds: ship_order, inventory_zero, lost_response, before_commit, restart.
    # Trigger after_preview or before_first_turn; order_id/variant_id required where relevant.
    fault_schedule: list[dict] = Field(default_factory=list)
    expected_state_invariants: dict
    # List of literal phrases required somewhere in assistant-visible text or operation notice.
    required_communications: list[str] = Field(default_factory=list)
    forbidden_events: list[str] = Field(
        default_factory=lambda: [
            "forbidden_tool_attempt",
            "invalid_tool_attempt",
            "unauthorized_commit_attempt",
        ]
    )
    max_turns: int = Field(default=8, ge=1, le=16)
    stop_conditions: list[str] = Field(
        default_factory=lambda: ["terminal_or_waiting_without_script"]
    )

    @model_validator(mode="after")
    def semantic_requirements(self):
        if self.clock.tzinfo is None:
            raise ValueError("clock must include timezone")
        if not self.hidden_user_goal or not self.expected_state_invariants:
            raise ValueError("scenario needs a goal and state oracle")
        return self


# expected_state_invariants keys supported by the independent grader:
# operation_count / application_count / refund_count / handoff_count (exact integers),
# order_id + order_status, action, target_variant, quantity, result (receipt result),
# inventory: {variant_id: {available?: int, reserved?: int}}.
# Any unrecognized assertion key is rejected, never silently ignored.
# required_communications uses literal alternatives separated by |, each item must match.
# fixture_changes: table orders/order_lines/inventory/variants, id, fields.
# Orders also accepts delivered_age_hours in fields; clock minus hours gives delivered_at.
