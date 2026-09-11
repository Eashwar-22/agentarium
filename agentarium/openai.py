"""Low-friction OpenAI Agents SDK entry points.

These functions keep a caller's existing agent and return value intact while
adding Agentarium lifecycle hooks around the runner call.
"""

from __future__ import annotations

from typing import Any

from agents import Agent, Runner

from .core import EventRecorder
from .dashboard import start_dashboard
from .env import load_env_file
from .openai_agents import AgentariumRunHooks, _short, observe_openai


def _question_from(input_value: object) -> str:
    """Make a safe run title from the input without requiring another argument."""

    return _short(input_value, limit=180) or "OpenAI Agents SDK run"


def run_sync(
    agent: Agent[Any],
    input: Any,
    *,
    event_path: str | None = None,
    question: str | None = None,
    show_dashboard: bool = True,
    dashboard_port: int | None = None,
    open_browser: bool = True,
    **runner_options: Any,
) -> Any:
    """Run one OpenAI agent synchronously while recording Agentarium events.

    This is a drop-in replacement for ``Runner.run_sync(agent, input, ...)``.
    It returns the original SDK result unchanged.
    """

    if "hooks" in runner_options:
        raise ValueError(
            "Agentarium supplies the SDK hooks for this run. "
            "Custom hooks are not composable in version 0.1."
        )

    load_env_file()
    recorder = EventRecorder(question or _question_from(input), event_path)
    hooks = AgentariumRunHooks(recorder)
    hooks.set_activity(agent, input)
    if show_dashboard:
        start_dashboard(
            recorder.event_path,
            port=dashboard_port,
            open_browser=open_browser,
        )
    recorder.start()
    try:
        result = Runner.run_sync(agent, input, hooks=hooks, **runner_options)
    except BaseException as exc:
        recorder.record_error(_short(exc), hooks.identify(agent))
        recorder.finish(succeeded=False)
        raise
    recorder.finish(succeeded=True)
    return result


async def run(
    agent: Agent[Any],
    input: Any,
    *,
    event_path: str | None = None,
    question: str | None = None,
    show_dashboard: bool = True,
    dashboard_port: int | None = None,
    open_browser: bool = True,
    **runner_options: Any,
) -> Any:
    """Run one OpenAI agent asynchronously while recording Agentarium events.

    This is a drop-in replacement for ``await Runner.run(agent, input, ...)``.
    It returns the original SDK result unchanged.
    """

    if "hooks" in runner_options:
        raise ValueError(
            "Agentarium supplies the SDK hooks for this run. "
            "Custom hooks are not composable in version 0.1."
        )

    load_env_file()
    recorder_path = EventRecorder(question or _question_from(input), event_path).event_path
    if show_dashboard:
        start_dashboard(
            recorder_path,
            port=dashboard_port,
            open_browser=open_browser,
        )
    async with observe_openai(question or _question_from(input), event_path) as observed:
        return await observed.run(agent, input, **runner_options)
