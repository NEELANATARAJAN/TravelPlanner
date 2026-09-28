"""
weather_agent.py
Weather agent using Open-Meteo (free, no API key). Handles geocoding
internally so the orchestrator only ever needs to pass a place name.
"""

import httpx

from src.travelai.agent.agent import Agent

_TOOLS = [
    {
        "name": "get_forecast",
        "description": "Get a daily weather forecast for a place between two dates (YYYY-MM-DD). Reliable only ~16 days out.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            "required": ["place", "start_date", "end_date"],
        },
    },
    {
        "name": "get_climate_normals",
        "description": "Get historical climate averages for a place and month. Use when the trip is too far out for get_forecast.",
        "input_schema": {
            "type": "object",
            "properties": {
                "place": {"type": "string"},
                "month": {"type": "integer", "description": "1-12"},
            },
            "required": ["place", "month"],
        },
    },
]

_SYSTEM_PROMPT = """You are a weather agent for a travel-planning system.
Given a place and date range, call get_forecast. If it reports the dates
are out of forecast range, call get_climate_normals instead. Return a
concise JSON summary per day (or per month, for normals): temperature
range, precipitation likelihood, and whether it's a live forecast or a
historical average. Never fabricate weather data yourself."""


def _geocode(place: str) -> dict:
    resp = httpx.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": place, "count": 1},
        timeout=10,
    )
    data = resp.json()
    if not data.get("results"):
        raise ValueError(f"Could not geocode '{place}'")
    r = data["results"][0]
    return {"lat": r["latitude"], "lon": r["longitude"], "name": r["name"], "country": r["country"]}


class WeatherAgent(Agent):
    name = "weather"
    system_prompt = _SYSTEM_PROMPT
    tools = _TOOLS

    def run_tool(self, name: str, tool_input: dict):
        if name == "get_forecast":
            return self._get_forecast(tool_input["place"], tool_input["start_date"], tool_input["end_date"])
        if name == "get_climate_normals":
            return self._get_climate_normals(tool_input["place"], tool_input["month"])
        raise ValueError(f"Unknown tool {name}")

    def _get_forecast(self, place: str, start_date: str, end_date: str) -> dict:
        loc = _geocode(place)
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                "timezone": "auto",
                "start_date": start_date,
                "end_date": end_date,
            },
            timeout=10,
        )
        data = resp.json()
        if "daily" not in data:
            return {"in_forecast_range": False, "place": f"{loc['name']}, {loc['country']}"}

        days = [
            {
                "date": date,
                "temp_max_c": data["daily"]["temperature_2m_max"][i],
                "temp_min_c": data["daily"]["temperature_2m_min"][i],
                "precip_probability": data["daily"]["precipitation_probability_max"][i],
            }
            for i, date in enumerate(data["daily"]["time"])
        ]
        return {"in_forecast_range": True, "place": f"{loc['name']}, {loc['country']}", "days": days}

    def _get_climate_normals(self, place: str, month: int) -> dict:
        loc = _geocode(place)
        resp = httpx.get(
            "https://climate-api.open-meteo.com/v1/climate",
            params={
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "start_date": "2015-01-01",
                "end_date": "2024-12-31",
                "models": "EC_Earth3P_HR",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            },
            timeout=15,
        )
        return {
            "place": f"{loc['name']}, {loc['country']}",
            "note": "Historical average, not a live forecast",
            "month": month,
            "raw": resp.json(),
        }
