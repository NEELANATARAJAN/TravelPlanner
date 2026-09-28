"""
agent.py
Minimal base class for a tool-using agent with pluggable LLM backend:


- "anthropic": Claude via Anthropic SDK
- "vllm": any tool-calling-capable open model served by vLLM's OpenAI compatible API

Every agent in this system (Retriever, Weather, Orchestrator) subclasses agent and only supplies a system prompt + tool schema + tool implementations
tool-calling loop and backend selection live here, so switching backends never touches the agents.

Select the backend with env var:
    export LLM_BACKEND=anthropic  # or vllm
    export LLM_BACKEND=vllm

For vLLM, also set:
    export VLLM_BASE_URL=http://localhost:8000/v1
    export VLLM_MODEL=meta-llama/Llama-3.1-8B-Instruct
"""

import json
from json import tool
import os

MODEL_ANTHROPIC = "claude-sonnet-4-6"
LLM_BACKEND = os.environ.get("LLM_BACKEND", "anthropic").lower()


class Agent:
    name: str = "agent"
    system_prompt: str = ""
    tools: list[dict] = []
    max_turns: int = 6

    def run_tool(self, name: str, tool_input: dict):
        """Override in subclass: dispatch a tool call to its implementation."""
        raise NotImplementedError

    def run(self, user_message: str) -> str:
        if LLM_BACKEND == "vllm":
            return self._run_vllm(user_message)
        else:
            return self._run_anthropic(user_message)

    # ----------------------------------------------------------------
    # Anthropic backend
    # ----------------------------------------------------------------

    def _run_anthropic(self, user_message: str) -> str:
        from anthropic import Anthropic
 
        client = Anthropic()  # reads ANTHROPIC_API_KEY from env
        messages = [{"role": "user", "content": user_message}]
 
        for _ in range(self.max_turns):
            response = client.messages.create(
                model=MODEL_ANTHROPIC,
                max_tokens=2000,
                system=self.system_prompt,
                tools=self.tools,
                messages=messages,
            )
 
            tool_uses = [b for b in response.content if b.type == "tool_use"]
 
            if not tool_uses:
                return "".join(b.text for b in response.content if b.type == "text")
 
            messages.append({"role": "assistant", "content": response.content})
 
            tool_results = []
            for use in tool_uses:
                try:
                    result = self.run_tool(use.name, use.input)
                except Exception as err:  # noqa: BLE001
                    result = {"error": str(err)}
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": use.id,
                        "content": json.dumps(result, default=str),
                    }
                )
            messages.append({"role": "user", "content": tool_results})
 
        return f"[{self.name}] Stopped after {self.max_turns} turns without a final answer."

    # ------------------------------------------------------------------
    # vLLM backend (OpenAI-compatible API)
    # ------------------------------------------------------------------
    def _run_vllm(self, user_message: str) -> str:
        from openai import OpenAI
 
        base_url = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
        model = os.environ.get("VLLM_MODEL")
        if not model:
            raise RuntimeError(
                "VLLM_MODEL env var is required when LLM_BACKEND=vllm "
                "(must match the model vLLM was started with, e.g. "
                "'meta-llama/Llama-3.1-8B-Instruct')"
            )
 
        client = OpenAI(base_url=base_url, api_key="not-needed")  # vLLM ignores the key by default
 
        openai_tools = [_anthropic_tool_to_openai(t) for t in self.tools]
 
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]
 
        for _ in range(self.max_turns):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=openai_tools if openai_tools else None,
                tool_choice="auto" if openai_tools else None,
                max_tokens=2000,
            )
 
            choice = response.choices[0]
            msg = choice.message
 
            if not msg.tool_calls:
                return msg.content or ""
 
            # Record the assistant turn (must include tool_calls verbatim
            # for the OpenAI-style protocol) then append one tool result
            # message per call.
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
 
            for tc in msg.tool_calls:
                try:
                    tool_input = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    result = self.run_tool(tc.function.name, tool_input)
                except Exception as err:  # noqa: BLE001
                    result = {"error": str(err)}
 
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    }
                )
 
        return f"[{self.name}] Stopped after {self.max_turns} turns without a final answer."

    def _anthropic_tool_to_openai(tool: dict) -> dict:
        """Convert an Anthropic-style tool schema (name/description/input_schema)
    into the OpenAI-style schema vLLM's API expects (function-wrapped)."""
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
                },
            }


    # def run(self, user_message: str) -> str:
    #     """
    #     Runs the agent's tool-calling loop until Claude stops requesting
    #     tools and returns a final text answer.
    #     """
    #     messages = [{"role": "user", "content": user_message}]

    #     for _ in range(self.max_turns):
    #         response = client.messages.create(
    #             model=MODEL,
    #             max_tokens=2000,
    #             system=self.system_prompt,
    #             tools=self.tools,
    #             messages=messages,
    #         )

    #         tool_uses = [b for b in response.content if b.type == "tool_use"]

    #         if not tool_uses:
    #             # Final answer — no more tools requested.
    #             return "".join(b.text for b in response.content if b.type == "text")

    #         messages.append({"role": "assistant", "content": response.content})

    #         tool_results = []
    #         for use in tool_uses:
    #             try:
    #                 result = self.run_tool(use.name, use.input)
    #             except Exception as err:  # noqa: BLE001
    #                 result = {"error": str(err)}
    #             tool_results.append(
    #                 {
    #                     "type": "tool_result",
    #                     "tool_use_id": use.id,
    #                     "content": json.dumps(result, default=str),
    #                 }
    #             )
    #         messages.append({"role": "user", "content": tool_results})

    #     return f"[{self.name}] Stopped after {self.max_turns} turns without a final answer."
