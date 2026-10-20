"""Explicit benchmark scope, independent of the product's nine-tool policy."""

from datetime import UTC, datetime

from aftercare.harness.contracts import digest

ALIASES = {
    "dashscope": "dashscope",
    "qwen": "dashscope",
    "openai/dashscope": "dashscope",
    "bailian-beijing-compatible": "dashscope",
    "dashscope-beijing": "dashscope",
}


def model_identity(provider, region, model):
    canonical = ALIASES.get(provider.lower())
    if canonical is None or region != "beijing" or not model:
        raise ValueError("UNAPPROVED_MODEL_IDENTITY")
    return f"{canonical}:{region}:{model}"


def plan_hash(plan):
    return digest({k: v for k, v in plan.items() if k != "plan_sha256"})


def authorize(plan, approval, account, source_hash):
    if plan_hash(plan) != plan.get("plan_sha256") or approval.get("plan_sha256") != plan_hash(plan):
        raise ValueError("PLAN_APPROVAL_HASH_MISMATCH")
    if approval.get("source") != "Explicit user message in this chat":
        raise ValueError("HUMAN_APPROVAL_REQUIRED")
    if plan.get("source_tree_hash") != source_hash:
        raise ValueError("SOURCE_HASH_MISMATCH")
    if plan.get("additional_paid_cost_cap_cny") != 0 or plan.get("concurrency") != 1:
        raise ValueError("SCOPE_NOT_SUPPORTED")
    if plan.get("retries") != 0 or plan.get("auto_review") is not False:
        raise ValueError("HIDDEN_CALLS_FORBIDDEN")
    if account.get("plan_sha256") != plan_hash(plan) or not account.get("FreeTierOnly"):
        raise ValueError("CURRENT_ACCOUNT_CONFIRMATION_REQUIRED")
    if account.get("confirmation_id") != plan.get("account_confirmation_id"):
        raise ValueError("ACCOUNT_CONFIRMATION_ID_MISMATCH")
    stamp = datetime.fromisoformat(account["confirmed_at"])
    age = (datetime.now(UTC) - stamp).total_seconds()
    if not 0 <= age <= 3600:
        raise ValueError("ACCOUNT_CONFIRMATION_EXPIRED")
    models = {}
    for _role, config in plan["roles"].items():
        if not config.get("enabled"):
            continue
        key = model_identity(config["provider"], config["region"], config["exact_model"])
        models[key] = models.get(key, 0) + config["batch_token_cap"]
        for name in ("batch_token_cap", "episode_token_cap", "request_cap", "output_cap"):
            if not isinstance(config.get(name), int) or config[name] <= 0:
                raise ValueError("INCOMPLETE_ROLE_LIMITS")
    for key, cap in models.items():
        if account.get("models", {}).get(key, {}).get("remaining", -1) < cap:
            raise ValueError("INSUFFICIENT_SHARED_MODEL_QUOTA")
    return models
