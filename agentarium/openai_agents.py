"""OpenAI Agents SDK adapter for Agentarium."""

from __future__ import annotations

import json
import re
from functools import wraps
from dataclasses import asdict, is_dataclass
from collections.abc import Mapping
from typing import Any

from agents import Agent, RunHooks, Runner

from .core import EventRecorder
from .capture import CapturePolicy
from .dashboard import start_dashboard
from .events import SourceInfo


_AUTO_HANDOFF = object()


def _recording_callback(callback):
    """Keep observation failures out of the SDK's workflow callbacks."""
    @wraps(callback)
    async def guarded(self, *args, **kwargs):
        if self.recorder.recording_error is not None:
            return
        try:
            await callback(self, *args, **kwargs)
        except Exception as error:
            self.recorder._disable_recording(error)
    return guarded


def _short(value: object, limit: int = 240) -> str:
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _tool_name(tool: object) -> str:
    return str(getattr(tool, "name", type(tool).__name__))


def _artifact_preview(value: object, limit: int = 1200) -> str:
    if hasattr(value, "model_dump_json"):
        text = value.model_dump_json(indent=2)
    else:
        text = str(value)
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _artifact_content(value: object) -> str:
    """Serialize an artifact without the dashboard preview limit."""

    return _recorded_content(value)


def _recorded_content(value: object) -> str:
    """Keep structured SDK data as JSON without shortening recorded payloads."""
    if isinstance(value, str):
        return value

    def serialize(item: object) -> object:
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        if is_dataclass(item):
            return asdict(item)
        return str(item)

    return json.dumps(value, default=serialize, indent=2, ensure_ascii=False)


def _sources_from_result(value: object, limit: int = 20) -> tuple[SourceInfo, ...]:
    """Extract source links from structured tool output without an LLM call."""

    parsed: object = value
    if hasattr(value, "model_dump"):
        parsed = value.model_dump()
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value

    found: list[SourceInfo] = []
    seen: set[str] = set()

    def add(url: object, title: object = None, snippet: object = None) -> None:
        clean_url = str(url or "").strip().rstrip(".,;:!?)\"]}")
        if not clean_url.startswith(("https://", "http://")) or clean_url in seen:
            return
        seen.add(clean_url)
        clean_title = _short(title or clean_url, limit=160)
        clean_snippet = _short(snippet, limit=280) if snippet else None
        found.append(SourceInfo(clean_title, clean_url, clean_snippet))

    def walk(item: object) -> None:
        if len(found) >= limit:
            return
        if isinstance(item, Mapping):
            direct_url = item.get("url") or item.get("uri") or item.get("href")
            if direct_url:
                add(
                    direct_url,
                    item.get("title") or item.get("name"),
                    item.get("content") or item.get("snippet") or item.get("evidence"),
                )
            for child in item.values():
                walk(child)
        elif isinstance(item, (list, tuple, set)):
            for child in item:
                walk(child)
        elif isinstance(item, str):
            for url in re.findall(r"https?://[^\s<>\"']+", item):
                add(url)

    walk(parsed)
    return tuple(found[:limit])


class AgentariumRunHooks(RunHooks):
    """Translate OpenAI lifecycle callbacks into Agentarium events."""

    def __init__(self, recorder: EventRecorder) -> None:
        self.recorder = recorder
        self._agent_ids: dict[int, str] = {}
        self._tool_calls: dict[tuple[str, str], str] = {}
        self._activities: dict[int, str] = {}
        self._full_activities: dict[int, str] = {}

    def set_activity(self, agent: Agent[Any], value: object) -> None:
        content = self._capture_text(value)
        self._activities[id(agent)] = _short(content, limit=800)
        self._full_activities[id(agent)] = content

    def _capture_text(self, value: object) -> str:
        try:
            return self.recorder.capture_policy.sanitize(_recorded_content(value))
        except Exception as error:
            self.recorder._disable_recording(error)
            return "[Payload capture unavailable]"

    def identify(self, agent: Agent[Any]) -> str:
        identity = id(agent)
        name = str(getattr(agent, "name", type(agent).__name__))
        agent_id = self.recorder.discover_agent(identity, name, getattr(agent, "handoff_description", None))
        self._agent_ids[identity] = agent_id
        return agent_id

    @_recording_callback
    async def on_agent_start(self, context: Any, agent: Agent[Any]) -> None:
        agent_id = self.identify(agent)
        self.recorder.start_task(
            agent_id,
            agent.name,
            self._activities.get(id(agent)),
            self._full_activities.get(id(agent)),
        )

    @_recording_callback
    async def on_llm_start(
        self,
        context: Any,
        agent: Agent[Any],
        system_prompt: str | None,
        input_items: list[Any],
    ) -> None:
        agent_id = self.identify(agent)
        model = str(getattr(agent, "model", None) or "SDK default")
        self.recorder.record_model_start(
            agent_id,
            agent.name,
            self._activities.get(id(agent)),
            len(input_items),
            model,
            self._full_activities.get(id(agent)),
            model_input_full=_recorded_content({"system_prompt": system_prompt, "input_items": input_items}),
        )

    @_recording_callback
    async def on_llm_end(
        self, context: Any, agent: Agent[Any], response: Any
    ) -> None:
        agent_id = self.identify(agent)
        usage = getattr(response, "usage", None)
        self.recorder.record_model_end(
            agent_id,
            agent.name,
            self._activities.get(id(agent)),
            len(getattr(response, "output", []) or []),
            int(getattr(usage, "input_tokens", 0) or 0),
            int(getattr(usage, "output_tokens", 0) or 0),
            int(getattr(usage, "total_tokens", 0) or 0),
            _recorded_content(response),
        )

    @_recording_callback
    async def on_agent_end(self, context: Any, agent: Agent[Any], output: Any) -> None:
        agent_id = self.identify(agent)
        output_name = type(output).__name__
        kind = "answer" if isinstance(output, str) else _short(output_name).lower()
        title = "final answer" if isinstance(output, str) else output_name
        self.recorder.record_artifact(
            agent_id,
            kind,
            title,
            preview=_artifact_preview(output),
            content=_artifact_content(output),
        )
        self.recorder.complete_task(agent_id, agent.name)

    @_recording_callback
    async def on_handoff(
        self, context: Any, from_agent: Agent[Any], to_agent: Agent[Any]
    ) -> None:
        source_id = self.identify(from_agent)
        target_id = self.identify(to_agent)
        self.recorder.complete_task(source_id, from_agent.name)
        self.recorder.handoff(
            source_id, target_id, from_agent.name, to_agent.name
        )

    @_recording_callback
    async def on_tool_start(self, context: Any, agent: Agent[Any], tool: Any) -> None:
        agent_id = self.identify(agent)
        call_id = str(getattr(context, "tool_call_id", "") or id(context))
        tool_name = _tool_name(tool)
        self._tool_calls[(agent_id, tool_name)] = call_id
        arguments = getattr(context, "tool_arguments", None)
        self.recorder.record_tool_start(
            agent_id,
            tool_name,
            call_id,
            _short(self._capture_text(arguments), limit=600) if arguments else None,
            getattr(tool, "description", None),
            _recorded_content(arguments) if arguments else None,
        )

    @_recording_callback
    async def on_tool_end(
        self, context: Any, agent: Agent[Any], tool: Any, result: object
    ) -> None:
        agent_id = self.identify(agent)
        tool_name = _tool_name(tool)
        context_call_id = getattr(context, "tool_call_id", "")
        call_id = str(
            context_call_id
            or self._tool_calls.get((agent_id, tool_name))
            or id(context)
        )
        self.recorder.record_tool_end(
            agent_id,
            tool_name,
            call_id,
            _short(self._capture_text(result), limit=600),
            sources=_sources_from_result(result),
            output_full=_recorded_content(result),
        )


class OpenAIAgentsObserver:
    """Run OpenAI agents while automatically recording their lifecycle."""

    def __init__(
        self,
        question: str,
        event_path: str | None = None,
        *,
        show_dashboard: bool = False,
        dashboard_port: int | None = None,
        open_browser: bool = True,
        capture_policy: CapturePolicy | None = None,
    ) -> None:
        self.recorder = EventRecorder(question, event_path, capture_policy=capture_policy)
        self.hooks = AgentariumRunHooks(self.recorder)
        self._previous_agent: Agent[Any] | None = None
        self._last_error: BaseException | None = None
        self._show_dashboard = show_dashboard
        self._dashboard_port = dashboard_port
        self._open_browser = open_browser

    async def __aenter__(self) -> "OpenAIAgentsObserver":
        if self._show_dashboard:
            start_dashboard(
                self.recorder.event_path,
                port=self._dashboard_port,
                open_browser=self._open_browser,
            )
        self.recorder.start()
        return self

    async def __aexit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> None:
        try:
            if exc is not None and exc is not self._last_error:
                self.recorder.record_error(_short(exc))
            self.recorder.finish(succeeded=exc is None)
        except Exception as recording_error:
            self.recorder._disable_recording(recording_error)

    async def run(
        self,
        agent: Agent[Any],
        input: Any,
        *,
        handoff_from: Agent[Any] | None | object = _AUTO_HANDOFF,
        **runner_options: Any,
    ) -> Any:
        """Run an agent with shared hooks.

        By default, consecutive calls are linked as a handoff. Pass
        ``handoff_from=None`` for independent work that runs in parallel, or
        pass an explicit source agent when the workflow graph branches.
        """
        try:
            self.hooks.set_activity(agent, input)
            source_agent = self._previous_agent if handoff_from is _AUTO_HANDOFF else handoff_from
            if source_agent is not None and source_agent is not agent:
                source_id = self.hooks.identify(source_agent)
                target_id = self.hooks.identify(agent)
                self.recorder.handoff(source_id, target_id, source_agent.name, agent.name)
            if handoff_from is not None:
                self._previous_agent = agent
        except Exception as recording_error:
            self.recorder._disable_recording(recording_error)

        try:
            return await Runner.run(agent, input, hooks=self.hooks, **runner_options)
        except BaseException as exc:
            self._last_error = exc
            try:
                agent_id = self.hooks.identify(agent)
                self.recorder.record_error(_short(exc), agent_id=agent_id)
            except Exception as recording_error:
                self.recorder._disable_recording(recording_error)
            raise


def observe_openai(
    question: str,
    event_path: str | None = None,
    *,
    show_dashboard: bool = False,
    dashboard_port: int | None = None,
    open_browser: bool = True,
    capture_policy: CapturePolicy | None = None,
) -> OpenAIAgentsObserver:
    """Create the multi-agent OpenAI wrapper.

    Set ``show_dashboard=True`` to start and open the local viewer with the
    workflow, without a separately managed Uvicorn terminal.
    """

    return OpenAIAgentsObserver(
        question,
        event_path,
        show_dashboard=show_dashboard,
        dashboard_port=dashboard_port,
        open_browser=open_browser,
        capture_policy=capture_policy,
    )
