"""A real parallel multi-agent workflow for stress-testing Agentarium.

The coordinator fans out to three independent research agents. Those agents
run at the same time, then their results merge into a synthesis, draft, review,
and final brief. Agentarium records the true fan-out and join instead of
pretending this is one long chain.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Type, TypeVar

from agents import Agent, function_tool
from pydantic import BaseModel, Field
from tavily import TavilyClient

from agentarium import load_env_file, observe_openai
from agentarium.events import EventType


DEFAULT_REQUEST = (
    "Should a 50-person online retailer adopt an AI support assistant in the "
    "next six months? Give a decision-ready recommendation."
)


class InvestigationPlan(BaseModel):
    decision: str
    audience: str
    market_query: str
    risk_query: str
    technical_query: str
    success_criteria: list[str] = Field(min_length=3, max_length=6)


class Source(BaseModel):
    title: str
    url: str
    evidence: str


class BranchReport(BaseModel):
    branch: str
    findings: list[str] = Field(min_length=2, max_length=5)
    sources: list[Source] = Field(min_length=2, max_length=5)
    uncertainties: list[str]


class CombinedAssessment(BaseModel):
    recommendation: str
    supporting_evidence: list[str] = Field(min_length=3, max_length=7)
    risks: list[str] = Field(min_length=2, max_length=6)
    open_questions: list[str]


class ReviewDecision(BaseModel):
    approved: bool
    strengths: list[str]
    corrections: list[str]


ModelType = TypeVar("ModelType", bound=BaseModel)


def _require_keys() -> None:
    load_env_file()
    missing = [
        name for name in ("OPENAI_API_KEY", "TAVILY_API_KEY") if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(
            f"Missing environment variable(s): {', '.join(missing)}. "
            "Load the existing .env file before running this workflow."
        )


def _search(query: str, lane: str) -> str:
    response = TavilyClient(api_key=os.environ["TAVILY_API_KEY"]).search(
        query=query,
        search_depth="basic",
        max_results=4,
        include_answer=False,
        include_raw_content=False,
    )
    results = [
        {
            "title": item.get("title", "Untitled source"),
            "url": item.get("url", ""),
            "content": item.get("content", "")[:1100],
        }
        for item in response.get("results", [])
    ]
    return json.dumps({"lane": lane, "query": query, "results": results})


@function_tool
def investigate_market(query: str) -> str:
    """Search for market, customer, and business-value evidence.

    Args:
        query: A focused market-research search query.
    """

    return _search(query, "market")


@function_tool
def investigate_risk(query: str) -> str:
    """Search for operational, legal, and customer-risk evidence.

    Args:
        query: A focused risk-research search query.
    """

    return _search(query, "risk")


@function_tool
def investigate_technical_fit(query: str) -> str:
    """Search for technical implementation and integration evidence.

    Args:
        query: A focused technical-research search query.
    """

    return _search(query, "technical")


coordinator = Agent(
    name="Decision Coordinator",
    handoff_description="Plans the research and assigns market, risk, and technical questions.",
    instructions=(
        "Turn the request into a concise investigation plan. Write one focused "
        "query each for market value, operational risk, and technical fit. Do "
        "not research or make the final recommendation."
    ),
    output_type=InvestigationPlan,
)

market_researcher = Agent(
    name="Market Researcher",
    handoff_description="Finds evidence about market value and adoption.",
    instructions=(
        "Use investigate_market exactly once with the supplied market query. "
        "Return only evidence from the tool results, exact source URLs, and "
        "uncertainties."
    ),
    tools=[investigate_market],
    output_type=BranchReport,
)

risk_researcher = Agent(
    name="Risk Researcher",
    handoff_description="Investigates operational, legal, and privacy risks.",
    instructions=(
        "Use investigate_risk exactly once with the supplied risk query. "
        "Focus on practical failure modes, legal or privacy concerns, and "
        "mitigations supported by the tool results. Keep exact source URLs."
    ),
    tools=[investigate_risk],
    output_type=BranchReport,
)

technical_researcher = Agent(
    name="Technical Researcher",
    handoff_description="Checks integration, evaluation, monitoring, and rollout feasibility.",
    instructions=(
        "Use investigate_technical_fit exactly once with the supplied technical "
        "query. Focus on integration, evaluation, monitoring, and rollout. "
        "Keep exact source URLs and state uncertainties."
    ),
    tools=[investigate_technical_fit],
    output_type=BranchReport,
)

evidence_synthesizer = Agent(
    name="Evidence Synthesizer",
    handoff_description="Combines the research into one assessment with open questions.",
    instructions=(
        "Merge the three branch reports into a balanced decision assessment. "
        "Separate supported evidence, material risks, and open questions. Do "
        "not invent facts or sources."
    ),
    output_type=CombinedAssessment,
)

draft_architect = Agent(
    name="Decision Architect",
    handoff_description="Drafts the recommendation and pilot plan from the evidence.",
    instructions=(
        "Turn the assessment into a short decision memo. Give a clear "
        "recommendation, conditions for proceeding, and a small pilot plan. "
        "Cite source URLs beside factual claims and label uncertainty."
    ),
)

quality_reviewer = Agent(
    name="Decision Reviewer",
    handoff_description="Checks the recommendation against the evidence and requests corrections.",
    instructions=(
        "Review the decision memo against the source assessment. Approve only "
        "if the recommendation is clear, claims are supported, risks are "
        "visible, and the pilot plan is practical. Otherwise give concise "
        "corrections."
    ),
    output_type=ReviewDecision,
)

final_writer = Agent(
    name="Final Brief Writer",
    handoff_description="Writes the final brief using the reviewed draft and feedback.",
    instructions=(
        "Write the final decision-ready brief using the draft and reviewer "
        "feedback. Apply every valid correction. Do not add unsupported claims "
        "or URLs. Keep it concise and useful for a small business leader."
    ),
)


def _expect_output(value: object, expected: Type[ModelType]) -> ModelType:
    if not isinstance(value, expected):
        raise RuntimeError(f"Expected {expected.__name__}, got {type(value).__name__}")
    return value


def _show(stage: str, value: object) -> None:
    print(f"\n{'=' * 12} {stage} {'=' * 12}")
    print(value.model_dump_json(indent=2) if isinstance(value, BaseModel) else value)


def _connect(observed: object, source: Agent, target: Agent, note: str) -> None:
    """Emit a real graph edge without making the target wait for other branches."""

    hooks = observed.hooks
    recorder = observed.recorder
    source_id = hooks.identify(source)
    target_id = hooks.identify(target)
    recorder.emit(
        EventType.MESSAGE_SENT,
        f"{source.name} sent context to {target.name}.",
        agent_id=source_id,
        target_agent_id=target_id,
        metadata={"note": note},
    )
    recorder.handoff(source_id, target_id, source.name, target.name)


async def run_parallel_due_diligence(request: str) -> str:
    """Run an eight-agent fan-out/fan-in workflow through Agentarium."""

    _require_keys()
    _show("REQUEST", request)

    async with observe_openai(request, show_dashboard=True) as observed:
        plan_result = await observed.run(coordinator, request)
        plan = _expect_output(plan_result.final_output, InvestigationPlan)
        _show("INVESTIGATION PLAN", plan)

        # These three handoffs create three independent lanes in the visual map.
        for specialist, note in (
            (market_researcher, "Investigate business value."),
            (risk_researcher, "Investigate risks and mitigations."),
            (technical_researcher, "Investigate technical fit."),
        ):
            _connect(observed, coordinator, specialist, note)

        common_context = (
            f"Original request:\n{request}\n\n"
            f"Investigation plan:\n{plan.model_dump_json(indent=2)}"
        )
        market_input = f"{common_context}\n\nMarket query: {plan.market_query}"
        risk_input = f"{common_context}\n\nRisk query: {plan.risk_query}"
        technical_input = f"{common_context}\n\nTechnical query: {plan.technical_query}"

        # No automatic handoff: these are genuinely concurrent branches.
        market_result, risk_result, technical_result = await asyncio.gather(
            observed.run(market_researcher, market_input, handoff_from=None, max_turns=5),
            observed.run(risk_researcher, risk_input, handoff_from=None, max_turns=5),
            observed.run(technical_researcher, technical_input, handoff_from=None, max_turns=5),
        )
        market = _expect_output(market_result.final_output, BranchReport)
        risk = _expect_output(risk_result.final_output, BranchReport)
        technical = _expect_output(technical_result.final_output, BranchReport)
        _show("MARKET LANE", market)
        _show("RISK LANE", risk)
        _show("TECHNICAL LANE", technical)

        for specialist in (market_researcher, risk_researcher, technical_researcher):
            _connect(observed, specialist, evidence_synthesizer, "Branch evidence ready.")

        synthesis_input = (
            f"Request:\n{request}\n\n"
            f"Market report:\n{market.model_dump_json(indent=2)}\n\n"
            f"Risk report:\n{risk.model_dump_json(indent=2)}\n\n"
            f"Technical report:\n{technical.model_dump_json(indent=2)}"
        )
        synthesis_result = await observed.run(
            evidence_synthesizer, synthesis_input, handoff_from=None, max_turns=4
        )
        assessment = _expect_output(synthesis_result.final_output, CombinedAssessment)
        _show("COMBINED ASSESSMENT", assessment)

        _connect(observed, evidence_synthesizer, draft_architect, "Assessment ready for a memo.")
        draft_result = await observed.run(
            draft_architect,
            f"Request:\n{request}\n\nAssessment:\n{assessment.model_dump_json(indent=2)}",
            handoff_from=None,
            max_turns=4,
        )
        draft = str(draft_result.final_output)
        _show("DECISION MEMO", draft)

        _connect(observed, draft_architect, quality_reviewer, "Memo ready for review.")
        review_result = await observed.run(
            quality_reviewer,
            f"Assessment:\n{assessment.model_dump_json(indent=2)}\n\nDraft memo:\n{draft}",
            handoff_from=None,
            max_turns=3,
        )
        review = _expect_output(review_result.final_output, ReviewDecision)
        _show("REVIEW", review)

        _connect(observed, quality_reviewer, final_writer, "Review feedback ready.")
        final_result = await observed.run(
            final_writer,
            f"Draft memo:\n{draft}\n\nReview decision:\n{review.model_dump_json(indent=2)}",
            handoff_from=None,
            max_turns=4,
        )
        final_brief = str(final_result.final_output)
        _show("FINAL BRIEF", final_brief)
        return final_brief


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an eight-agent parallel due-diligence workflow."
    )
    parser.add_argument("request", nargs="*", help="Optional decision request.")
    args = parser.parse_args()
    request = " ".join(args.request).strip() or DEFAULT_REQUEST

    try:
        asyncio.run(run_parallel_due_diligence(request))
    except KeyboardInterrupt:
        raise SystemExit("\nStopped by user.") from None
    except Exception as exc:
        raise SystemExit(f"\nWorkflow failed: {exc}") from exc


if __name__ == "__main__":
    main()
