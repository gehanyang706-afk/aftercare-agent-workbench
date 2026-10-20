"""Version-isolated paired metrics; missing usage is never zero."""

import math
from collections import Counter


def wilson(successes, n):
    if not n:
        return None
    z = 1.959963984540054
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [centre - half, centre + half]


def summarize(rows):
    if not rows:
        return {"coverage": {}, "paired": {}}
    versions = {r["experiment_version"] for r in rows}
    trials = {r["trial"] for r in rows}
    if len(versions) != 1 or len(trials) != 1:
        raise ValueError("MIXED_VERSION_OR_TRIAL")
    keys = [(r["task_id"], r["variant"], r["trial"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("DUPLICATE_EPISODE")
    variants = sorted({r["variant"] for r in rows})
    report = {"coverage": {}, "variants": {}, "paired": {}}
    for variant in variants:
        group = [r for r in rows if r["variant"] == variant]
        evaluated = [r for r in group if r.get("official_reward") is not None]
        successes = sum(r["official_reward"] == 1 for r in evaluated)
        report["coverage"][variant] = {
            "planned": len(group),
            "attempted": sum(r["status"] != "not_run" for r in group),
            "completed": len(evaluated),
            "not_run": sum(r["status"] == "not_run" for r in group),
        }
        roles = {}
        for role in ("agent", "user", "judge", "auxiliary"):
            calls = [r.get("roles", {}).get(role, {}) for r in group]
            roles[role] = {
                "known_tokens": sum(c.get("known_tokens", 0) for c in calls),
                "unknown_reserved": sum(c.get("unknown_reserved", 0) for c in calls),
                "http_requests": sum(c.get("http_requests", 0) for c in calls),
            }
        report["variants"][variant] = {
            "successes": successes,
            "evaluated": len(evaluated),
            "success_rate": successes / len(evaluated) if evaluated else None,
            "wilson": wilson(successes, len(evaluated)),
            "roles": roles,
        }
    if len(variants) == 2:
        a = "official_tc" if "official_tc" in variants else variants[0]
        b = next(v for v in variants if v != a)
        ga = {r["task_id"]: r for r in rows if r["variant"] == a}
        gb = {r["task_id"]: r for r in rows if r["variant"] == b}
        pairs = [
            (ga[k], gb[k])
            for k in sorted(ga.keys() & gb.keys())
            if ga[k].get("official_reward") is not None and gb[k].get("official_reward") is not None
        ]
        counts = Counter(
            f"{int(x['official_reward'] == 1)}{int(y['official_reward'] == 1)}" for x, y in pairs
        )
        both = [(x, y) for x, y in pairs if x["official_reward"] == y["official_reward"] == 1]

        def saving(pairs_):
            if (
                not pairs_
                or any(
                    not isinstance(r.get("roles", {}).get("agent", {}).get("known_tokens"), int)
                    for pair in pairs_
                    for r in pair
                )
                or any(
                    r.get("roles", {}).get("agent", {}).get("unknown_reserved", 0)
                    for pair in pairs_
                    for r in pair
                )
            ):
                return None
            totals = [
                sum(
                    pair[i].get("roles", {}).get("agent", {}).get("known_tokens", 0)
                    for pair in pairs_
                )
                for i in (0, 1)
            ]
            return 100 * (1 - totals[1] / totals[0]) if totals[0] else None

        complete = len(pairs) == len(ga) == len(gb)
        report["paired"] = {
            "variant_order": [a, b],
            "counts": dict(counts),
            "valid_pairs": len(pairs),
            "both_success_n": len(both),
            "agent_token_saving_pct": saving(pairs) if complete else None,
            "both_success_agent_token_saving_pct": saving(both),
            "success_delta_pp": 100
            * sum(y["official_reward"] - x["official_reward"] for x, y in pairs)
            / len(pairs)
            if complete and pairs
            else None,
        }
    return report


def repeated_reads(events):
    """Mutation sequence is part of a repeat key; writes invalidate comparisons."""
    seen, repeats = set(), 0
    for e in events:
        key = (e["name"], e["canonical_arguments"], e["mutation_sequence"])
        if e["is_read"]:
            repeats += key in seen
            seen.add(key)
    return repeats
