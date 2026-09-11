"""A second, unrelated workflow used to test the Agentarium wrapper."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import List, Type, TypeVar

from agents import Agent, function_tool
from pydantic import BaseModel, Field
from tavily import TavilyClient

from agentarium import load_env_file, observe_openai


DEFAULT_REQUEST = (
    "Plan a relaxed three-day autumn trip to Copenhagen for two people, "
    "focused on food and design."
)


class TripRequest(BaseModel):
    """The Router's normalized version of the user's request."""

    destination: str
    timing: str
    travelers: str
    interests: List[str] = Field(min_length=1)
    weather_query: str
    places_query: str


class WeatherBrief(BaseModel):
    """Current weather context gathered by the Weather Specialist."""

    summary: str
    packing_advice: List[str]
    source_urls: List[str]


class TravelBrief(BaseModel):
    """Places and practical advice gathered by the Travel Advisor."""

    recommendations: List[str] = Field(min_length=2)
    practical_notes: List[str]
    source_urls: List[str]


def _search(query: str) -> str:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set")

    response = TavilyClient(api_key=api_key).search(
        query=query,
        search_depth="basic",
        max_results=4,
        include_answer=False,
        include_raw_content=False,
    )
    results = [
        {
            "title": item.get("title", "Untitled result"),
            "url": item.get("url", ""),
            "content": item.get("content", "")[:1200],
        }
        for item in response.get("results", [])
    ]
    return json.dumps({"query": query, "results": results})


@function_tool
def check_destination_weather(query: str) -> str:
    """Search for current or seasonal weather information.

    Args:
        query: A destination and date-specific weather search query.
    """

    return _search(query)


@function_tool
def find_local_places(query: str) -> str:
    """Search for relevant places and current practical information.

    Args:
        query: A destination search query containing the traveler's interests.
    """

    return _search(query)


router = Agent(
    name="Request Router",
    instructions=(
        "Normalize the travel request for specialist agents. Extract the "
        "destination, timing, travelers, and interests. Write one focused "
        "weather query and one focused places query. Do not plan the trip."
    ),
    output_type=TripRequest,
)


weather_specialist = Agent(
    name="Weather Specialist",
    instructions=(
        "Use check_destination_weather exactly once with the supplied query. "
        "Summarize only the returned evidence, give practical packing advice, "
        "and preserve the source URLs. Do not invent a forecast."
    ),
    tools=[check_destination_weather],
    output_type=WeatherBrief,
)


travel_advisor = Agent(
    name="Travel Advisor",
    instructions=(
        "Use find_local_places exactly once with the supplied query. Suggest "
        "places that match the interests, include practical notes, and preserve "
        "the returned source URLs. Do not invent places or opening hours."
    ),
    tools=[find_local_places],
    output_type=TravelBrief,
)


final_composer = Agent(
    name="Itinerary Composer",
    instructions=(
        "Create a concise three-day itinerary using only the supplied weather "
        "and places briefs. Keep the schedule relaxed. Cite source URLs beside "
        "relevant recommendations and clearly mark uncertain details."
    ),
)


ModelType = TypeVar("ModelType", bound=BaseModel)


def _expect_output(value: object, expected: Type[ModelType]) -> ModelType:
    if not isinstance(value, expected):
        raise RuntimeError(
            f"Expected {expected.__name__}, got {type(value).__name__}"
        )
    return value


def _require_keys() -> None:
    load_env_file()
    missing = [
        name
        for name in ("OPENAI_API_KEY", "TAVILY_API_KEY")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(
            f"Missing environment variable(s): {', '.join(missing)}. "
            "Load the existing .env file before running this workflow."
        )


def _show(stage: str, value: object) -> None:
    print(f"\n{'=' * 12} {stage} {'=' * 12}")
    if isinstance(value, BaseModel):
        print(value.model_dump_json(indent=2))
    else:
        print(value)


async def run_travel_workflow(request: str) -> str:
    """Run Router -> Weather Specialist -> Travel Advisor -> Composer."""

    _require_keys()
    _show("TRAVEL REQUEST", request)

    # This is the only integration point. Agentarium discovers every agent,
    # tool, artifact, model call, and handoff from SDK lifecycle callbacks.
    async with observe_openai(request, show_dashboard=True) as observed:
        route_result = await observed.run(router, request, max_turns=3)
        trip = _expect_output(route_result.final_output, TripRequest)
        _show("ROUTED REQUEST", trip)

        weather_result = await observed.run(
            weather_specialist,
            (
                f"Destination: {trip.destination}\n"
                f"Timing: {trip.timing}\n"
                f"Weather query: {trip.weather_query}"
            ),
            max_turns=5,
        )
        weather = _expect_output(weather_result.final_output, WeatherBrief)
        _show("WEATHER BRIEF", weather)

        places_result = await observed.run(
            travel_advisor,
            (
                f"Destination: {trip.destination}\n"
                f"Timing: {trip.timing}\n"
                f"Interests: {', '.join(trip.interests)}\n"
                f"Places query: {trip.places_query}"
            ),
            max_turns=5,
        )
        places = _expect_output(places_result.final_output, TravelBrief)
        _show("TRAVEL BRIEF", places)

        composer_input = (
            f"Original request:\n{request}\n\n"
            f"Normalized request:\n{trip.model_dump_json(indent=2)}\n\n"
            f"Weather brief:\n{weather.model_dump_json(indent=2)}\n\n"
            f"Places brief:\n{places.model_dump_json(indent=2)}"
        )
        final_result = await observed.run(
            final_composer, composer_input, max_turns=3
        )
        itinerary = str(final_result.final_output)
        _show("FINAL ITINERARY", itinerary)
        return itinerary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a travel workflow through the Agentarium wrapper."
    )
    parser.add_argument(
        "request",
        nargs="*",
        help="Travel request. A Copenhagen example is used when omitted.",
    )
    args = parser.parse_args()
    request = " ".join(args.request).strip() or DEFAULT_REQUEST

    try:
        asyncio.run(run_travel_workflow(request))
    except KeyboardInterrupt:
        raise SystemExit("\nStopped by user.") from None
    except Exception as exc:
        raise SystemExit(f"\nWorkflow failed: {exc}") from exc


if __name__ == "__main__":
    main()
