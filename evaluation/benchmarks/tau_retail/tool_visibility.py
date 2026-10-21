"""Pure visible-observation routing. Visibility is neither authorization nor execution."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from aftercare.harness.contracts import canonical, digest

RULE_VERSION = "state-aware-tools-v1"
STRICT_PENDING = {"cancel_pending_order", "modify_pending_order_items"}
LOOSE_PENDING = {"modify_pending_order_address", "modify_pending_order_payment"}
DELIVERED = {"return_delivered_order_items", "exchange_delivered_order_items"}
ORDER_WRITES = STRICT_PENDING | LOOSE_PENDING | DELIVERED
ALWAYS = {
    "calculate",
    "find_user_id_by_email",
    "find_user_id_by_name_zip",
    "get_order_details",
    "get_product_details",
    "get_item_details",
    "get_user_details",
    "list_all_product_types",
    "modify_user_address",
    "transfer_to_human_agents",
}
# Exact spellings from fixed tools.py, not inferred from arbitrary substrings.
KNOWN_STATUSES = {
    "pending",
    "pending (item modified)",
    "delivered",
    "processed",
    "cancelled",
    "exchange requested",
    "return requested",
}
ORDER_RESULTS = ORDER_WRITES | {"get_order_details"}


def rule_hash():
    return digest(
        {
            "version": RULE_VERSION,
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
    )


@dataclass(frozen=True)
class OrderObservation:
    order_id: str
    status: str
    tool_call_id: str
    tool_name: str
    sequence: int
    content_hash: str
    supersedes_call_id: str | None = None


@dataclass(frozen=True)
class ObservedOrderState:
    orders: tuple[OrderObservation, ...]
    observations: tuple[OrderObservation, ...]
    historical_tools: tuple[str, ...]
    pending_calls: tuple[str, ...]
    fallback_reasons: tuple[str, ...]
    errors: tuple[str, ...]


def observe_visible_history(history):
    calls, pending, orders, observations, used, fallback, errors = {}, set(), {}, [], set(), [], []
    ambiguous_calls = set()
    for sequence, message in enumerate(history):
        if message.get("role") == "assistant":
            batch_orders = {}
            for call in message.get("tool_calls") or []:
                try:
                    cid, fn = call["id"], call["function"]
                    name, args = fn["name"], fn.get("arguments", {})
                    if isinstance(args, str):
                        args = json.loads(args)
                    if not isinstance(args, dict) or cid in calls:
                        raise ValueError("bad arguments or duplicate call id")
                    calls[cid] = (name, args)
                    used.add(name)
                    pending.add(cid)
                    if name in ORDER_RESULTS and isinstance(args.get("order_id"), str):
                        batch_orders.setdefault(args["order_id"], []).append(cid)
                except (KeyError, TypeError, ValueError):
                    fallback.append("unparseable_tool_call")
            for oid, ids in batch_orders.items():
                if len(ids) > 1:
                    # Result list order is not a proof of parallel execution order.
                    fallback.append("ambiguous_same_batch_order_results")
                    ambiguous_calls.update(ids)
                    orders.pop(oid, None)
        if message.get("role") != "tool":
            continue
        cid = message.get("tool_call_id")
        if cid not in calls or cid not in pending:
            fallback.append("unpaired_tool_result")
            continue
        pending.remove(cid)
        name, args = calls[cid]
        if name not in ORDER_RESULTS or cid in ambiguous_calls:
            continue
        content = message.get("content")
        try:
            result = json.loads(content) if isinstance(content, str) else None
        except (ValueError, TypeError):
            result = None
        if (
            message.get("error")
            or (isinstance(result, str) and result.startswith("Error:"))
            or (isinstance(result, dict) and result.get("error"))
        ):
            errors.append(cid)
            fallback.append("order_tool_error")
            continue
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("order_id"), str)
            or not isinstance(result.get("status"), str)
        ):
            fallback.append("unparseable_order_result")
            continue
        oid, status = result["order_id"], result["status"]
        if args.get("order_id") != oid:
            fallback.append("order_entity_mismatch")
            continue
        if status not in KNOWN_STATUSES:
            fallback.append("unknown_order_status")
            continue
        previous = orders.get(oid)
        observation = OrderObservation(
            oid,
            status,
            cid,
            name,
            sequence,
            digest(content),
            previous.tool_call_id if previous else None,
        )
        orders[oid] = observation
        observations.append(observation)
    if pending:
        fallback.append("pending_tool_results")
    return ObservedOrderState(
        tuple(orders.values()),
        tuple(observations),
        tuple(sorted(used)),
        tuple(sorted(pending)),
        tuple(sorted(set(fallback))),
        tuple(errors),
    )


@dataclass(frozen=True)
class ToolVisibilityDecision:
    visible_names: tuple[str, ...]
    hidden: dict
    selected_evidence: dict
    fallback_reasons: tuple[str, ...]
    rule_version: str
    rule_hash: str
    catalog_hash: str
    selected_schema_hash: str
    original_schema_bytes: int
    selected_schema_bytes: int

    def to_dict(self):
        return asdict(self)


def select_tool_names(state, official_catalog):
    names = [t["function"]["name"] for t in official_catalog]
    fallback = list(state.fallback_reasons)
    if set(names) != ALWAYS | ORDER_WRITES or len(set(names)) != len(names):
        fallback.append("catalog_mapping_uncertain")
    if set(state.historical_tools) - set(names):
        fallback.append("historical_tool_outside_catalog")
    allowed = set(ALWAYS) | set(state.historical_tools)
    evidence = {}
    for order in state.orders:
        capabilities = set()
        if order.status == "pending":
            capabilities |= STRICT_PENDING | LOOSE_PENDING
        elif order.status == "pending (item modified)":
            capabilities |= LOOSE_PENDING
        elif order.status == "delivered":
            capabilities |= DELIVERED
        for tool in capabilities:
            allowed.add(tool)
            evidence.setdefault(tool, []).append(asdict(order))
    if fallback:
        allowed.update(names)
    selected = [t for t in official_catalog if t["function"]["name"] in allowed]
    hidden = {
        n: {
            "reason": "no_observed_eligible_order",
            "latest_observations": [asdict(o) for o in state.orders],
        }
        for n in names
        if n not in allowed
    }
    return ToolVisibilityDecision(
        tuple(t["function"]["name"] for t in selected),
        hidden,
        evidence,
        tuple(sorted(set(fallback))),
        RULE_VERSION,
        rule_hash(),
        digest(official_catalog),
        digest(selected),
        len(canonical(official_catalog).encode()),
        len(canonical(selected).encode()),
    )


class ToolVisibilityPolicy:
    def select(self, history, official_catalog):
        return select_tool_names(observe_visible_history(history), official_catalog)


def validate_catalog_subset(tools, catalog, expected_catalog_hash, expected_rule_hash):
    if digest(catalog) != expected_catalog_hash or rule_hash() != expected_rule_hash:
        raise ValueError("TOOL_VISIBILITY_HASH_MISMATCH")
    approved = {t["function"]["name"]: t for t in catalog}
    seen = set()
    for tool in tools:
        name = tool.get("function", {}).get("name")
        if name in seen or name not in approved or tool != approved[name]:
            raise ValueError("TOOL_SCHEMA_NOT_APPROVED_SUBSET")
        seen.add(name)
    if not seen:
        raise ValueError("EMPTY_TOOL_VISIBILITY")
