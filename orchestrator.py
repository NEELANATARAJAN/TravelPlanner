"""
orchestrator.py
The top-level agent. Instead of calling raw APIs directly, its "tools"
are two other agents (RetrieverAgent, WeatherAgent) — the classic
"agents-as-tools" orchestration pattern. Each sub-agent runs its own
internal tool-use loop and returns a distilled result; the orchestrator
never sees the sub-agents' raw API calls, only their summarized output.

This keeps concerns cleanly separated:
  - RetrieverAgent owns "how do we find grounded facts" (RAG strategy)
  - WeatherAgent owns "how do we get weather" (forecast vs. climate fallback)
  - Orchestrator owns "what does the user need, and how do I combine it"

Swapping RAG backends, weather providers, or adding a PlacesAgent later
means changing/adding one file — the orchestrator's tool schema and
delegation logic barely change.
"""

from agent import Agent
from retriever_agent import RetrieverAgent
from weather_agent import WeatherAgent

_TOOLS = [
    {
        "name": "consult_retriever_agent",
        "description": (
            "Delegate to the retrieval agent to get grounded destination facts "
            "(sights, food, practical tips) from the travel guide corpus. "
            "Always use this instead of relying on your own memory for destination facts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "Natural-language info need, e.g. 'indoor food options and temple sights in Kyoto'",
                }
            },
            "required": ["request"],
        },
    },
    {
        "name": "consult_weather_agent",
        "description": (
            "Delegate to the weather agent to get forecast or climate-normal data "
            "for the trip dates and destination. Always call this before finalizing "
            "day-by-day outdoor/indoor choices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "e.g. 'forecast for Kyoto, Japan from 2026-06-10 to 2026-06-12'",
                }
            },
            "required": ["request"],
        },
    },
]

_SYSTEM_PROMPT = """You are the orchestrator agent for an AI travel planner.
You do not call raw APIs yourself — you delegate to two specialist agents:

- consult_retriever_agent: grounded destination facts (RAG over a guide corpus)
- consult_weather_agent: live forecast or historical climate data

Workflow:
1. Always consult the retriever agent for destination facts relevant to the
   user's interests (sights, food, practical tips).
2. Always consult the weather agent for the trip's date range.
3. Combine both: build a day-by-day itinerary that matches activities to
   weather (indoor alternatives on high-precipitation days, outdoor sights
   on clear days) and is grounded in the retrieved guide content.
4. If weather data came back as a historical average rather than a live
   forecast, say so explicitly to the user.
5. Be concise. Do not add generic travel advice that isn't grounded in
   what the sub-agents returned.
"""


class OrchestratorAgent(Agent):
    name = "orchestrator"
    system_prompt = _SYSTEM_PROMPT
    tools = _TOOLS

    def __init__(self):
        self.retriever = RetrieverAgent()
        self.weather = WeatherAgent()

    def run_tool(self, name: str, tool_input: dict):
        if name == "consult_retriever_agent":
            return self.retriever.run(tool_input["request"])
        if name == "consult_weather_agent":
            return self.weather.run(tool_input["request"])
        raise ValueError(f"Unknown tool {name}")


def plan_trip(user_request: str) -> str:
    """Convenience entry point: run the full multi-agent workflow."""
    orchestrator = OrchestratorAgent()
    return orchestrator.run(user_request)
