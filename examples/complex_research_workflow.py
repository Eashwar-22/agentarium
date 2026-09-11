"""A larger real workflow for stress-testing the Agentarium wrapper.

This example intentionally uses different agent names, two tools, explicit
agent-to-agent messages, and one optional review/revision loop. The frontend
does not know any of these names in advance.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import List, Type, TypeVar
from urllib.parse import urlparse

from agents import Agent, function_tool
from pydantic import BaseModel, Field
from tavily import TavilyClient

from agentarium import load_env_file, observe_openai
from agentarium.events import EventType


DEFAULT_QUESTION = (
    "What should a small European ecommerce company consider before adopting "
    "AI customer-support agents?"
)


class ResearchBrief(BaseModel):
    question: str
    audience: str
    decision_to_support: str
    constraints: List[str] = Field(min_length=2, max_length=5)


class SearchPlan(BaseModel):
    objective: str
    queries: List[str] = Field(min_length=2, max_length=3)
    evidence_needed: List[str] = Field(min_length=2, max_length=5)


class EvidenceSource(BaseModel):
    title: str
    url: str
    evidence: str


class EvidenceBundle(BaseModel):
    findings: List[str] = Field(min_length=2, max_length=6)
    sources: List[EvidenceSource] = Field(min_length=3, max_length=8)
    gaps: List[str]


class EvidenceAssessment(BaseModel):
    supported_claims: List[str] = Field(min_length=2, max_length=6)
    caveats: List[str] = Field(min_length=1, max_length=5)
    quality_summary: str


class ReviewDecision(BaseModel):
    approved: bool
    strengths: List[str]
    revision_notes: List[str]


ModelType = TypeVar("ModelType", bound=BaseModel)


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
            "Load your existing .env file before running this workflow."
        )


def _search(query: str) -> str:
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
            "content": item.get("content", "")[:1000],
            "score": item.get("score"),
        }
        for item in response.get("results", [])
    ]
    return json.dumps({"query": query, "results": results})


@function_tool
def search_evidence(query: str) -> str:
    """Find current web evidence for a focused research question.

    Args:
        query: One focused web-search query.
    """

    return _search(query)


@function_tool
def score_source_domains(urls: List[str]) -> str:
    """Classify source domains using transparent, deterministic rules.

    Args:
        urls: Exact source URLs collected by the Web Researcher.
    """

    official_suffixes = (".gov", ".edu", ".europa.eu", ".org")
    scored = []
    for url in urls:
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        if domain.endswith(official_suffixes):
            tier = "primary or institutional"
        elif domain:
            tier = "commercial or editorial"
        else:
            tier = "unknown"
        scored.append({"url": url, "domain": domain or "unknown", "tier": tier})
    return json.dumps({"sources": scored})


intake_analyst = Agent(
    name="Intake Analyst",
    instructions=(
        "Turn the user's question into a compact research brief. Identify the "
        "audience, the decision they need to make, and practical constraints. "
        "Do not research or answer the question."
    ),
    output_type=ResearchBrief,
)


research_planner = Agent(
    name="Research Planner",
    instructions=(
        "Create a focused evidence plan from the supplied brief. Write two or "
        "three distinct search queries, covering benefits, risks, and relevant "
        "rules or implementation considerations. Do not answer the question."
    ),
    output_type=SearchPlan,
)


web_researcher = Agent(
    name="Web Researcher",
    instructions=(
        "Use search_evidence at least twice with different queries from the "
        "plan. Keep only claims supported by the returned results, preserve "
        "exact URLs, and state evidence gaps clearly."
    ),
    tools=[search_evidence],
    output_type=EvidenceBundle,
)


evidence_analyst = Agent(
    name="Evidence Analyst",
    instructions=(
        "Use score_source_domains exactly once on the collected source URLs. "
        "Then identify which claims are supported, which claims need caution, "
        "and summarize the evidence quality. Do not invent evidence."
    ),
    tools=[score_source_domains],
    output_type=EvidenceAssessment,
)


draft_writer = Agent(
    name="Draft Writer",
    instructions=(
        "Write a practical, balanced briefing from the supplied brief, "
        "evidence bundle, and assessment. Use short sections and cite exact "
        "source URLs beside factual claims. Clearly label uncertainty."
    ),
)


quality_reviewer = Agent(
    name="Quality Reviewer",
    instructions=(
        "Review the draft against the brief. Check whether it is useful, "
        "balanced, properly caveated, and supported by citations. Approve only "
        "if it meets every criterion; otherwise request concise, actionable "
        "revisions."
    ),
    output_type=ReviewDecision,
)


def _expect_output(value: object, expected: Type[ModelType]) -> ModelType:
    if not isinstance(value, expected):
        raise RuntimeError(f"Expected {expected.__name__}, got {type(value).__name__}")
    return value


def _show(stage: str, value: object) -> None:
    print(f"\n{'=' * 12} {stage} {'=' * 12}")
    if isinstance(value, BaseModel):
        print(value.model_dump_json(indent=2))
    else:
        print(value)


def _send_message(observed: object, source: Agent, target: Agent, note: str) -> None:
    """Record a user-safe agent-to-agent message for the visual flow map."""

    hooks = observed.hooks
    recorder = observed.recorder
    source_id = hooks.identify(source)
    target_id = hooks.identify(target)
    recorder.emit(
        EventType.MESSAGE_SENT,
        f"{source.name} sent a note to {target.name}.",
        agent_id=source_id,
        target_agent_id=target_id,
        metadata={"note": note},
    )


def _begin_revision(observed: object, note: str) -> None:
    """Mark the Writer's second pass as a real, observable retry."""

    hooks = observed.hooks
    recorder = observed.recorder
    hooks.set_activity(draft_writer, note)
    writer_id = hooks.identify(draft_writer)
    task_id = recorder.start_task(writer_id, draft_writer.name, note)
    recorder.emit(
        EventType.RETRYING,
        "Draft Writer started a revision pass.",
        agent_id=writer_id,
        task_id=task_id,
        metadata={"reason": note},
    )


async def run_complex_research_workflow(question: str) -> str:
    """Run six agents and allow Quality Reviewer to request one revision."""

    _require_keys()
    _show("QUESTION", question)

    async with observe_openai(question, show_dashboard=True) as observed:
        intake_result = await observed.run(intake_analyst, question, max_turns=3)
        brief = _expect_output(intake_result.final_output, ResearchBrief)
        _show("INTAKE BRIEF", brief)

        _send_message(observed, intake_analyst, research_planner, "Brief ready")
        plan_result = await observed.run(
            research_planner, brief.model_dump_json(indent=2), max_turns=3
        )
        plan = _expect_output(plan_result.final_output, SearchPlan)
        _show("RESEARCH PLAN", plan)

        _send_message(observed, research_planner, web_researcher, "Search plan ready")
        researcher_input = (
            f"Research brief:\n{brief.model_dump_json(indent=2)}\n\n"
            f"Search plan:\n{plan.model_dump_json(indent=2)}"
        )
        research_result = await observed.run(
            web_researcher, researcher_input, max_turns=10
        )
        evidence = _expect_output(research_result.final_output, EvidenceBundle)
        _show("WEB EVIDENCE", evidence)

        _send_message(observed, web_researcher, evidence_analyst, "Evidence bundle ready")
        assessment_result = await observed.run(
            evidence_analyst,
            (
                f"Research brief:\n{brief.model_dump_json(indent=2)}\n\n"
                f"Evidence bundle:\n{evidence.model_dump_json(indent=2)}"
            ),
            max_turns=6,
        )
        assessment = _expect_output(assessment_result.final_output, EvidenceAssessment)
        _show("EVIDENCE ASSESSMENT", assessment)

        _send_message(observed, evidence_analyst, draft_writer, "Evidence checked")
        writer_input = (
            f"Research brief:\n{brief.model_dump_json(indent=2)}\n\n"
            f"Evidence bundle:\n{evidence.model_dump_json(indent=2)}\n\n"
            f"Evidence assessment:\n{assessment.model_dump_json(indent=2)}"
        )
        draft_result = await observed.run(draft_writer, writer_input, max_turns=4)
        draft = str(draft_result.final_output)
        _show("DRAFT", draft)

        _send_message(observed, draft_writer, quality_reviewer, "Draft ready for review")
        review_result = await observed.run(
            quality_reviewer,
            f"Research brief:\n{brief.model_dump_json(indent=2)}\n\nDraft:\n{draft}",
            max_turns=3,
        )
        review = _expect_output(review_result.final_output, ReviewDecision)
        _show("QUALITY REVIEW", review)

        if not review.approved:
            revision_note = "; ".join(review.revision_notes) or "Improve the draft."
            _send_message(observed, quality_reviewer, draft_writer, "Revision requested")
            _begin_revision(observed, revision_note)
            revised_result = await observed.run(
                draft_writer,
                (
                    f"Original draft:\n{draft}\n\n"
                    f"Reviewer notes:\n{revision_note}\n\n"
                    "Return the revised briefing with the same citation rules."
                ),
                max_turns=4,
            )
            draft = str(revised_result.final_output)
            _show("REVISED DRAFT", draft)

        _show("FINAL BRIEFING", draft)
        return draft


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a six-agent research workflow through Agentarium."
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="Research question. A demo question is used when omitted.",
    )
    args = parser.parse_args()
    question = " ".join(args.question).strip() or DEFAULT_QUESTION

    try:
        asyncio.run(run_complex_research_workflow(question))
    except KeyboardInterrupt:
        raise SystemExit("\nStopped by user.") from None
    except Exception as exc:
        raise SystemExit(f"\nWorkflow failed: {exc}") from exc


if __name__ == "__main__":
    main()
