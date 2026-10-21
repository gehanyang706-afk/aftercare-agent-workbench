"""The real upstream LLMAgent, without a decision or prompt wrapper."""

from tau2.agent.llm_agent import LLMAgent


def create_baseline(*, tools, domain_policy, llm, llm_args=None):
    return LLMAgent(tools=tools, domain_policy=domain_policy, llm=llm, llm_args=llm_args)
