"""A playful, three-agent Agentarium demo.

Pipeline:
Researcher -> Conspiracist -> Debunker

Run with:
    python -m examples.random_agent_chaos "why cats knock things off tables"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from agents import Agent, function_tool
from tavily import TavilyClient

from agentarium import load_env_file, observe_openai


DEFAULT_TOPIC = "why cats knock things off tables"


def _require_keys() -> None:
    load_env_file()
    missing = [
        key
        for key in ("OPENAI_API_KEY", "TAVILY_API_KEY")
        if not os.environ.get(key)
    ]
    if missing:
        raise RuntimeError(f"Missing environment variable(s): {', '.join(missing)}")


@function_tool
def search_web(query: str) -> str:
    """Search Tavily and return compact, source-linked results.

    Args:
        query: A focused web-search query.
    """

    response = TavilyClient(api_key=os.environ["TAVILY_API_KEY"]).search(
        query=query,
        max_results=5,
        search_depth="basic",
        include_answer=False,
        include_raw_content=False,
    )
    results = [
        {
            "title": item.get("title", "Untitled source"),
            "url": item.get("url", ""),
            "content": item.get("content", "")[:700],
        }
        for item in response.get("results", [])
    ]
    return json.dumps({"query": query, "results": results})


researcher = Agent(
    name="Researcher",
    instructions=(
        "You are a no-nonsense research assistant. Use search_web to gather "
        "3–5 real, verifiable facts about the user's topic. Return a tight "
        "bullet list. Keep exact source URLs next to the facts they support. "
        "Do not invent claims or URLs."
    ),
    tools=[search_web],
)

conspiracist = Agent(
    name="Conspiracist",
    instructions=(
        "You are an over-caffeinated conspiracy-theory podcaster. You receive "
        "real facts and turn them into an absurd, obviously fictional joke "
        "conspiracy. Keep it harmless, good-natured, and never target real "
        "people or groups. Write 2–3 short paragraphs."
    ),
)

debunker = Agent(
    name="Debunker",
    instructions=(
        "You are a deadpan, dry-humored fact-checker. You receive original "
        "facts and a silly conspiracy theory. Roast the theory using the facts, "
        "without being cruel. Finish with a one-line Unhinged-ness score out of "
        "10."
    ),
)


def _show(stage: str, value: object) -> None:
    print(f"\n{'=' * 12} {stage} {'=' * 12}")
    print(value)


async def run_chaos(topic: str) -> None:
    """Run the playful workflow while Agentarium records its full story."""

    _require_keys()
    _show("TOPIC", topic)

    # Agentarium discovers the agents, records their work, extracts Tavily URLs,
    # and opens the dashboard. No frontend agent names are hard-coded.
    async with observe_openai(topic, show_dashboard=True) as observed:
        research_result = await observed.run(researcher, topic, max_turns=6)
        facts = str(research_result.final_output)
        _show("RESEARCHER", facts)

        conspiracy_result = await observed.run(
            conspiracist,
            f"TOPIC:\n{topic}\n\nREAL FACTS:\n{facts}",
            max_turns=3,
        )
        theory = str(conspiracy_result.final_output)
        _show("CONSPIRACIST", theory)

        debunk_result = await observed.run(
            debunker,
            f"TOPIC:\n{topic}\n\nREAL FACTS:\n{facts}\n\n"
            f"CONSPIRACY THEORY:\n{theory}",
            max_turns=3,
        )
        _show("DEBUNKER", debunk_result.final_output)


def main() -> None:
    topic = " ".join(sys.argv[1:]).strip() or DEFAULT_TOPIC
    try:
        asyncio.run(run_chaos(topic))
    except KeyboardInterrupt:
        raise SystemExit("\nStopped by user.") from None
    except Exception as exc:
        raise SystemExit(f"\nChaos workflow failed: {exc}") from exc


if __name__ == "__main__":
    main()
