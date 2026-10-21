from evaluation.benchmarks.tau_retail.adapter import create_agent
from evaluation.benchmarks.tau_retail.baseline import create_baseline

VARIANTS = {
    "official_tc": create_baseline,
    "tool_visibility_v1": lambda **kw: create_agent(tool_visibility=True, **kw),
    "harness_full_history": create_agent,
    "harness_fixed_window": lambda **kw: create_agent(policy_id="fixed_window", **kw),
    "harness_evidence": lambda **kw: create_agent(policy_id="evidence_projection", **kw),
}
