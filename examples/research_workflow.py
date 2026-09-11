"""A small, real multi-agent research workflow.

This file is intentionally separate from Agentarium. It gives us a real workflow
to observe later, once the visual wrapper is ready.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import List, Optional, Type, TypeVar

from agents import Agent, function_tool
from pydantic import BaseModel, Field
from tavily import TavilyClient

from agentarium import load_env_file, observe_openai


DEFAULT_QUESTION = (
    "Is lab-grown meat environmentally better than conventional meat?"
)


class ResearchPlan(BaseModel):
    """The Planner's instructions for the Scout."""

    objective: str
    search_queries: List[str] = Field(min_length=1, max_length=3)
    success_criteria: List[str] = Field(min_length=1)


class Source(BaseModel):
    """One web source selected by the Scout."""

    title: str
    url: str
    evidence: str


class ScoutReport(BaseModel):
    """Evidence collected by the Scout."""

    summary: str
    sources: List[Source]
    gaps: List[str]


class Critique(BaseModel):
    """The Critic's decision about the Scout's evidence."""

    accepted: bool
    reason: str
    missing_information: List[str]
    retry_query: Optional[str]


@function_tool
def search_web(query: str) -> str:
    """Search the live web for evidence.

    Args:
        query: A focused search query written for a web search engine.

    Returns:
        JSON containing titles, URLs, evidence snippets, and relevance scores.
    """

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set")

    response = TavilyClient(api_key=api_key).search(
        query=query,
        search_depth="basic",
        max_results=5,
        include_answer=False,
        include_raw_content=False,
    )

    # Return only what the Scout needs. This keeps the LLM input small and makes
    # the tool result easy to inspect later in Agentarium.
    results = []
    for item in response.get("results", []):
        results.append(
            {
                "title": item.get("title", "Untitled source"),
                "url": item.get("url", ""),
                "content": item.get("content", "")[:1500],
                "score": item.get("score"),
            }
        )

    return json.dumps({"query": query, "results": results})


planner = Agent(
    name="Planner",
    instructions=(
        "You plan small evidence-based research tasks. Turn the user's question "
        "into exactly two focused web-search queries. State what a good answer "
        "must establish. Do not answer the question yourself."
    ),
    output_type=ResearchPlan,
)


scout = Agent(
    name="Scout",
    instructions=(
        "You collect web evidence for a research question. You must call "
        "search_web at least once. Prefer credible, relevant sources and keep "
        "their exact URLs. Report only claims supported by the returned search "
        "results. Clearly list gaps instead of guessing."
    ),
    tools=[search_web],
    output_type=ScoutReport,
)


critic = Agent(
    name="Critic",
    instructions=(
        "You are a strict evidence critic. Accept a Scout report only if it "
        "addresses the original question, has multiple relevant sources, and "
        "does not overstate its evidence. If you reject it, explain the missing "
        "information and provide one focused retry query. If you accept it, set "
        "retry_query to null."
    ),
    output_type=Critique,
)


writer = Agent(
    name="Writer",
    instructions=(
        "Write a short, balanced answer using only the supplied Scout evidence. "
        "Use Markdown links to cite source URLs beside the claims they support. "
        "Do not invent facts or URLs. If the final Critic still rejected the "
        "evidence, say what remains uncertain."
    ),
)


ModelType = TypeVar("ModelType", bound=BaseModel)


def _require_keys() -> None:
    load_env_file()
    missing = [
        name
        for name in ("OPENAI_API_KEY", "TAVILY_API_KEY")
        if not os.environ.get(name)
    ]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Missing environment variable(s): {names}. "
            "See REAL_WORKFLOW.md for setup."
        )


def _expect_output(value: object, expected: Type[ModelType]) -> ModelType:
    if not isinstance(value, expected):
        raise RuntimeError(
            f"Expected {expected.__name__}, got {type(value).__name__}"
        )
    return value


def _show(stage: str, value: object) -> None:
    print(f"\n{'=' * 14} {stage} {'=' * 14}")
    if isinstance(value, BaseModel):
        print(value.model_dump_json(indent=2))
    else:
        print(value)


async def run_research_workflow(question: str) -> str:
    """Run Planner -> Scout -> Critic -> optional retry -> Writer."""

    _require_keys()
    _show("QUESTION", question)

    async with observe_openai(question, show_dashboard=True) as observed:
        plan_result = await observed.run(planner, question, max_turns=3)
        plan = _expect_output(plan_result.final_output, ResearchPlan)
        _show("PLANNER", plan)

        scout_input = (
            f"Original question:\n{question}\n\n"
            f"Planner output:\n{plan.model_dump_json(indent=2)}"
        )
        scout_result = await observed.run(scout, scout_input, max_turns=8)
        report = _expect_output(scout_result.final_output, ScoutReport)
        _show("SCOUT", report)

        critique_input = (
            f"Original question:\n{question}\n\n"
            f"Scout report:\n{report.model_dump_json(indent=2)}"
        )
        critique_result = await observed.run(critic, critique_input, max_turns=3)
        review = _expect_output(critique_result.final_output, Critique)
        _show("CRITIC", review)

        # One retry is enough to demonstrate a loop without risking endless agent
        # activity. The Critic may still reject the second report.
        if not review.accepted:
            retry_input = (
                f"Original question:\n{question}\n\n"
                f"Original plan:\n{plan.model_dump_json(indent=2)}\n\n"
                f"Previous report:\n{report.model_dump_json(indent=2)}\n\n"
                f"Critic feedback:\n{review.model_dump_json(indent=2)}\n\n"
                "Search again using the Critic's retry query. Return one revised "
                "report that combines useful old evidence with the new evidence."
            )
            retry_result = await observed.run(scout, retry_input, max_turns=6)
            report = _expect_output(retry_result.final_output, ScoutReport)
            _show("SCOUT RETRY", report)

            second_critique_input = (
                f"Original question:\n{question}\n\n"
                f"Revised Scout report:\n{report.model_dump_json(indent=2)}"
            )
            second_critique_result = await observed.run(
                critic, second_critique_input, max_turns=3
            )
            review = _expect_output(second_critique_result.final_output, Critique)
            _show("FINAL CRITIC", review)

        writer_input = (
            f"Original question:\n{question}\n\n"
            f"Research plan:\n{plan.model_dump_json(indent=2)}\n\n"
            f"Final Scout report:\n{report.model_dump_json(indent=2)}\n\n"
            f"Final Critic decision:\n{review.model_dump_json(indent=2)}"
        )
        writer_result = await observed.run(writer, writer_input, max_turns=3)
        answer = str(writer_result.final_output)
        _show("WRITER - FINAL ANSWER", answer)
        return answer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a real Planner/Scout/Critic/Writer research workflow."
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="Research question. A demo question is used when omitted.",
    )
    args = parser.parse_args()
    question = " ".join(args.question).strip() or DEFAULT_QUESTION

    try:
        asyncio.run(run_research_workflow(question))
    except KeyboardInterrupt:
        raise SystemExit("\nStopped by user.") from None
    except Exception as exc:
        raise SystemExit(f"\nWorkflow failed: {exc}") from exc


if __name__ == "__main__":
    main()
