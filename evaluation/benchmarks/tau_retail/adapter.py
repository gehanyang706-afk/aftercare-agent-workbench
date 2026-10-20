"""Official half-duplex participant. No environment or business executor is reachable."""

from copy import deepcopy

from tau2.agent.base_agent import HalfDuplexAgent
from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT, LLMAgentState
from tau2.data_model.message import MultiToolMessage, SystemMessage
from tau2.utils import llm_utils

from aftercare.harness.context_policy import ContextPolicy
from aftercare.harness.contracts import ContextInput
from aftercare.harness.message_blocks import message_blocks


class RetailAgent(HalfDuplexAgent):
    def __init__(
        self,
        tools,
        domain_policy,
        llm,
        llm_args=None,
        policy_id="full_history",
        trace=None,
        context_limit=200000,
        tool_visibility=False,
    ):
        super().__init__(tools=tools, domain_policy=domain_policy)
        self.llm, self.llm_args = llm, dict(llm_args or {})
        self.policy, self.trace, self.context_limit = ContextPolicy(policy_id), trace, context_limit
        self.tool_visibility = tool_visibility

    def set_seed(self, seed):
        self.llm_args["seed"] = seed

    def get_init_state(self, message_history=None):
        from tau2.agent.base_agent import is_valid_agent_history_message

        history = deepcopy(message_history or [])
        if not all(is_valid_agent_history_message(m) for m in history):
            raise ValueError("INVALID_VISIBLE_HISTORY")
        return LLMAgentState(
            system_messages=[
                SystemMessage(
                    role="system",
                    content=SYSTEM_PROMPT.format(
                        agent_instruction=AGENT_INSTRUCTION, domain_policy=self.domain_policy
                    ),
                )
            ],
            messages=history,
        )

    def generate_next_message(self, message, state):
        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        else:
            state.messages.append(message)
        raw = llm_utils.to_litellm_messages(state.messages)
        selected_tools = self.tools
        if self.tool_visibility:
            from evaluation.benchmarks.tau_retail.tool_visibility import ToolVisibilityPolicy

            observed = deepcopy(raw)
            for converted, original in zip(observed, state.messages, strict=True):
                if converted.get("role") == "tool":
                    converted["error"] = getattr(original, "error", False)
            decision = ToolVisibilityPolicy().select(
                observed, [t.openai_schema for t in self.tools]
            )
            selected_tools = [t for t in self.tools if t.name in decision.visible_names]
            if self.trace:
                self.trace.emit("tools.visibility", decision.to_dict())
        prepared = self.policy.build(
            ContextInput(
                raw, state.system_messages[0].content, [t.openai_schema for t in selected_tools]
            ),
            self.context_limit,
        )
        # Retain the official message objects/conversion/parser; only select whole blocks
        # and normalize content. No custom tool execution or hidden task in this state.
        blocks = message_blocks(raw)
        indexes, offset = [], 0
        for block, selection in zip(blocks, prepared.selection_manifest, strict=True):
            if selection["kept"]:
                indexes.extend(range(offset, offset + len(block)))
            offset += len(block)
        visible = [deepcopy(state.messages[i]) for i in indexes]
        for original, projected in zip(visible, prepared.messages[1:], strict=True):
            original.content = projected.get("content")
        if self.trace:
            self.trace.emit(
                "context.prepared",
                {
                    "policy_id": prepared.policy_id,
                    "estimated_size": prepared.estimated_size,
                    "selection_manifest": prepared.selection_manifest,
                },
            )
        result = llm_utils.generate(
            model=self.llm,
            tools=selected_tools,
            messages=state.system_messages + visible,
            call_name="agent_response",
            **self.llm_args,
        )
        state.messages.append(result)
        return result, state


def create_agent(
    *,
    tools,
    domain_policy,
    llm,
    llm_args=None,
    policy_id="full_history",
    trace=None,
    tool_visibility=False,
    **untrusted_factory_fields,
):
    # Official build_agent passes task/audio fields. They are deliberately never retained.
    return RetailAgent(
        tools=tools,
        domain_policy=domain_policy,
        llm=llm,
        llm_args=llm_args,
        policy_id=policy_id,
        trace=trace,
        tool_visibility=tool_visibility,
    )
