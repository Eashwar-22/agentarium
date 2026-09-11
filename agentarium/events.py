"""Framework-independent event contract for Agentarium workflows."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "0.2"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"0.1", SCHEMA_VERSION})


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    AGENT_SPAWNED = "agent_spawned"
    TASK_STARTED = "task_started"
    MODEL_STARTED = "model_started"
    MODEL_COMPLETED = "model_completed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    ARTIFACT_CREATED = "artifact_created"
    MESSAGE_SENT = "message_sent"
    HANDOFF_STARTED = "handoff_started"
    WAITING = "waiting"
    RETRYING = "retrying"
    ERROR = "error"
    TASK_COMPLETED = "task_completed"
    AGENT_COMPLETED = "agent_completed"
    RUN_COMPLETED = "run_completed"


@dataclass(frozen=True)
class SourceInfo:
    """One source observed in a tool result."""

    title: str
    url: str
    snippet: str | None = None


@dataclass(frozen=True)
class ToolInfo:
    """Observable information about one tool call, without hidden reasoning."""

    name: str
    call_id: str
    input_summary: str | None = None
    output_summary: str | None = None
    sources: tuple[SourceInfo, ...] = ()


@dataclass(frozen=True)
class ArtifactInfo:
    """A source, plan, answer, or other output created during a run."""

    artifact_id: str
    kind: str
    title: str
    uri: str | None = None
    preview: str | None = None


@dataclass(frozen=True)
class ErrorInfo:
    """A user-safe description of an observable failure."""

    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class AgentEvent:
    """One immutable fact emitted by an agent workflow."""

    run_id: str
    event_id: str
    sequence: int
    timestamp: datetime
    type: EventType
    summary: str
    agent_id: str | None = None
    task_id: str | None = None
    tool: ToolInfo | None = None
    target_agent_id: str | None = None
    artifact: ArtifactInfo | None = None
    error: ErrorInfo | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible wire representation."""
        event = asdict(self)
        event["timestamp"] = self.timestamp.isoformat()
        event["type"] = self.type.value
        return event

    def to_json(self) -> str:
        """Serialize the event using the compact JSON wire format."""
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AgentEvent":
        """Parse one event from its wire representation."""
        allowed = {
            "schema_version", "run_id", "event_id", "sequence", "timestamp",
            "type", "summary", "agent_id", "task_id", "tool",
            "target_agent_id", "artifact", "error", "metadata",
        }
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"Unknown event field(s): {', '.join(sorted(unknown))}")

        required = {
            "schema_version", "run_id", "event_id", "sequence", "timestamp",
            "type", "summary",
        }
        missing = required - set(raw)
        if missing:
            raise ValueError(f"Missing event field(s): {', '.join(sorted(missing))}")

        try:
            event = cls(
                schema_version=str(raw["schema_version"]),
                run_id=str(raw["run_id"]),
                event_id=str(raw["event_id"]),
                sequence=int(raw["sequence"]),
                timestamp=datetime.fromisoformat(str(raw["timestamp"])),
                type=EventType(str(raw["type"])),
                summary=str(raw["summary"]),
                agent_id=_optional_string(raw.get("agent_id")),
                task_id=_optional_string(raw.get("task_id")),
                tool=_tool_info(raw.get("tool")),
                target_agent_id=_optional_string(raw.get("target_agent_id")),
                artifact=_nested_dataclass(ArtifactInfo, raw.get("artifact")),
                error=_nested_dataclass(ErrorInfo, raw.get("error")),
                metadata=dict(raw.get("metadata") or {}),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid event data: {exc}") from exc

        validate_event(event)
        return event

    @classmethod
    def from_json(cls, raw: str) -> "AgentEvent":
        """Parse one event from JSON."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid event JSON: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise ValueError("An event JSON value must be an object")
        return cls.from_dict(data)


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _nested_dataclass(model: Any, value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{model.__name__} must be an object")
    return model(**value)


def _tool_info(value: Any) -> ToolInfo | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("ToolInfo must be an object")
    tool = dict(value)
    raw_sources = tool.pop("sources", ()) or ()
    if not isinstance(raw_sources, (list, tuple)):
        raise ValueError("ToolInfo.sources must be a list")
    sources = tuple(_nested_dataclass(SourceInfo, source) for source in raw_sources)
    return ToolInfo(**tool, sources=sources)


def _require_text(value: str | None, field_name: str, event: AgentEvent) -> None:
    if value is None or not value.strip():
        raise ValueError(f"Event {event.event_id!r} requires non-empty {field_name}")


def validate_event(event: AgentEvent) -> None:
    """Validate the shape and event-type requirements of one event."""
    _require_text(event.run_id, "run_id", event)
    _require_text(event.event_id, "event_id", event)
    _require_text(event.summary, "summary", event)

    if event.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(
            f"Event {event.event_id!r} uses schema {event.schema_version!r}; "
            f"supported versions are {sorted(SUPPORTED_SCHEMA_VERSIONS)!r}"
        )
    if event.sequence < 1:
        raise ValueError(f"Event {event.event_id!r} sequence must be positive")
    if event.timestamp.tzinfo is None or event.timestamp.utcoffset() is None:
        raise ValueError(f"Event {event.event_id!r} timestamp must include a timezone")
    if event.agent_id and event.target_agent_id == event.agent_id:
        raise ValueError(f"Event {event.event_id!r} cannot target its own agent")

    run_events = {EventType.RUN_STARTED, EventType.RUN_COMPLETED}
    agent_events = {
        EventType.AGENT_SPAWNED, EventType.TASK_STARTED,
        EventType.MODEL_STARTED, EventType.MODEL_COMPLETED,
        EventType.TOOL_STARTED, EventType.TOOL_COMPLETED,
        EventType.ARTIFACT_CREATED, EventType.MESSAGE_SENT,
        EventType.HANDOFF_STARTED, EventType.WAITING, EventType.RETRYING,
        EventType.TASK_COMPLETED, EventType.AGENT_COMPLETED,
    }
    task_events = {
        EventType.TASK_STARTED, EventType.TOOL_STARTED,
        EventType.MODEL_STARTED, EventType.MODEL_COMPLETED,
        EventType.TOOL_COMPLETED, EventType.ARTIFACT_CREATED,
        EventType.WAITING, EventType.RETRYING, EventType.TASK_COMPLETED,
    }

    if event.type in run_events and event.agent_id is not None:
        raise ValueError(f"Run event {event.event_id!r} must not have agent_id")
    if event.type in agent_events:
        _require_text(event.agent_id, "agent_id", event)
    if event.type in task_events:
        _require_text(event.task_id, "task_id", event)
    if event.type in {EventType.TOOL_STARTED, EventType.TOOL_COMPLETED}:
        if event.tool is None:
            raise ValueError(f"Tool event {event.event_id!r} requires tool")
        _require_text(event.tool.name, "tool.name", event)
        _require_text(event.tool.call_id, "tool.call_id", event)
        for source in event.tool.sources:
            _require_text(source.title, "tool.sources.title", event)
            _require_text(source.url, "tool.sources.url", event)
    if event.type == EventType.ARTIFACT_CREATED:
        if event.artifact is None:
            raise ValueError(f"Artifact event {event.event_id!r} requires artifact")
        _require_text(event.artifact.artifact_id, "artifact.artifact_id", event)
        _require_text(event.artifact.kind, "artifact.kind", event)
        _require_text(event.artifact.title, "artifact.title", event)
    if event.type in {EventType.MESSAGE_SENT, EventType.HANDOFF_STARTED}:
        _require_text(event.target_agent_id, "target_agent_id", event)
    if event.type == EventType.ERROR:
        if event.error is None:
            raise ValueError(f"Error event {event.event_id!r} requires error")
        _require_text(event.error.code, "error.code", event)
        _require_text(event.error.message, "error.message", event)

    try:
        json.dumps(event.to_dict())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Event {event.event_id!r} is not JSON serializable: {exc}") from exc


def validate_event_sequence(events: Iterable[AgentEvent]) -> None:
    """Validate a complete, ordered run suitable for replay."""
    ordered = list(events)
    if not ordered:
        raise ValueError("Event sequence must not be empty")
    for event in ordered:
        validate_event(event)

    if len({event.run_id for event in ordered}) != 1:
        raise ValueError("All events in a sequence must share one run_id")
    event_ids = [event.event_id for event in ordered]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("Every event_id in a sequence must be unique")

    expected = list(range(1, len(ordered) + 1))
    actual = [event.sequence for event in ordered]
    if actual != expected:
        raise ValueError(f"Sequence numbers must be contiguous from 1; got {actual}")
    for previous, current in zip(ordered, ordered[1:]):
        if current.timestamp < previous.timestamp:
            raise ValueError(
                f"Timestamp moved backward between {previous.event_id!r} "
                f"and {current.event_id!r}"
            )

    if ordered[0].type != EventType.RUN_STARTED:
        raise ValueError("The first event must be run_started")
    if ordered[-1].type != EventType.RUN_COMPLETED:
        raise ValueError("The final event must be run_completed")
    if sum(event.type == EventType.RUN_STARTED for event in ordered) != 1:
        raise ValueError("A complete run must contain exactly one run_started event")
    if sum(event.type == EventType.RUN_COMPLETED for event in ordered) != 1:
        raise ValueError("A complete run must contain exactly one run_completed event")

    spawned_agents: set[str] = set()
    completed_agents: set[str] = set()
    started_tasks: set[tuple[str, str]] = set()
    active_tools: set[tuple[str, str]] = set()

    for event in ordered:
        agent_id = event.agent_id
        if event.type == EventType.AGENT_SPAWNED:
            assert agent_id is not None
            if agent_id in spawned_agents:
                raise ValueError(f"Agent {agent_id!r} was spawned more than once")
            spawned_agents.add(agent_id)
            continue

        if agent_id is not None:
            if agent_id not in spawned_agents:
                raise ValueError(
                    f"Agent {agent_id!r} emitted {event.type.value!r} before agent_spawned"
                )
            if agent_id in completed_agents:
                raise ValueError(f"Agent {agent_id!r} emitted an event after agent_completed")
        if event.target_agent_id and event.target_agent_id not in spawned_agents:
            raise ValueError(
                f"Target agent {event.target_agent_id!r} was not spawned before "
                f"event {event.event_id!r}"
            )

        if event.type == EventType.TASK_STARTED:
            assert agent_id is not None and event.task_id is not None
            task_key = (agent_id, event.task_id)
            if task_key in started_tasks:
                raise ValueError(f"Task {event.task_id!r} started more than once for {agent_id!r}")
            started_tasks.add(task_key)
        if event.task_id and event.type not in {EventType.TASK_STARTED, EventType.ERROR}:
            if agent_id is None or (agent_id, event.task_id) not in started_tasks:
                raise ValueError(
                    f"Task {event.task_id!r} for {agent_id!r} was used before task_started"
                )

        if event.type == EventType.TOOL_STARTED:
            assert agent_id is not None and event.tool is not None
            tool_key = (agent_id, event.tool.call_id)
            if tool_key in active_tools:
                raise ValueError(f"Tool call {event.tool.call_id!r} started more than once")
            active_tools.add(tool_key)
        elif event.type == EventType.TOOL_COMPLETED:
            assert agent_id is not None and event.tool is not None
            tool_key = (agent_id, event.tool.call_id)
            if tool_key not in active_tools:
                raise ValueError(f"Tool call {event.tool.call_id!r} completed before tool_started")
            active_tools.remove(tool_key)
        elif event.type == EventType.AGENT_COMPLETED:
            assert agent_id is not None
            completed_agents.add(agent_id)

    if active_tools:
        unresolved = ", ".join(call_id for _, call_id in sorted(active_tools))
        raise ValueError(f"Run completed with unfinished tool call(s): {unresolved}")


def create_demo_events() -> list[AgentEvent]:
    """Create a representative run containing every Stage 2 event type."""
    run_id = "run-demo-001"
    started_at = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
    events: list[AgentEvent] = []

    def emit(event_type: EventType, summary: str, **details: Any) -> None:
        sequence = len(events) + 1
        events.append(AgentEvent(
            run_id=run_id,
            event_id=f"evt-{sequence:03d}",
            sequence=sequence,
            timestamp=started_at + timedelta(seconds=sequence - 1),
            type=event_type,
            summary=summary,
            **details,
        ))

    emit(EventType.RUN_STARTED, "Research run started.", metadata={"question": "How does urban heat affect city health?"})
    for agent_id, role in (("planner", "Planner"), ("scout", "Scout"), ("critic", "Critic"), ("writer", "Writer")):
        emit(EventType.AGENT_SPAWNED, f"{role} joined the run.", agent_id=agent_id, metadata={"role": role})

    emit(EventType.TASK_STARTED, "Planner began creating the research plan.", agent_id="planner", task_id="task-plan")
    emit(EventType.MODEL_STARTED, "Planner asked the model to create a research plan.", agent_id="planner", task_id="task-plan", metadata={"input_items": 1})
    emit(EventType.MODEL_COMPLETED, "Planner received the structured plan.", agent_id="planner", task_id="task-plan", metadata={"output_items": 1, "total_tokens": 420})
    plan = ArtifactInfo("artifact-plan", "plan", "Urban heat research plan")
    emit(EventType.ARTIFACT_CREATED, "Planner created a research plan.", agent_id="planner", task_id="task-plan", artifact=plan)
    emit(EventType.MESSAGE_SENT, "Planner sent search instructions to Scout.", agent_id="planner", target_agent_id="scout", metadata={"message": "Find current, credible health evidence."})
    emit(EventType.TASK_COMPLETED, "Planner completed the research plan.", agent_id="planner", task_id="task-plan")
    emit(EventType.AGENT_COMPLETED, "Planner finished its assigned work.", agent_id="planner")

    emit(EventType.TASK_STARTED, "Scout began searching for evidence.", agent_id="scout", task_id="task-search")
    emit(EventType.TOOL_STARTED, "Scout started the first search.", agent_id="scout", task_id="task-search", tool=ToolInfo("web_search", "call-search-001", "urban heat health effects"))
    emit(EventType.TOOL_COMPLETED, "The first search returned eight results.", agent_id="scout", task_id="task-search", tool=ToolInfo("web_search", "call-search-001", output_summary="8 candidate results"))
    sources = ArtifactInfo("artifact-sources-001", "source_bundle", "Initial urban heat sources")
    emit(EventType.ARTIFACT_CREATED, "Scout collected the initial sources.", agent_id="scout", task_id="task-search", artifact=sources)
    emit(EventType.HANDOFF_STARTED, "Scout handed sources to Critic.", agent_id="scout", target_agent_id="critic", artifact=sources)
    emit(EventType.WAITING, "Scout waited for source review.", agent_id="scout", task_id="task-search", metadata={"waiting_for": "critic"})

    emit(EventType.TASK_STARTED, "Critic began reviewing the sources.", agent_id="critic", task_id="task-review")
    emit(EventType.ERROR, "Critic found a gap in the evidence.", agent_id="critic", task_id="task-review", error=ErrorInfo("weak_evidence", "One claim lacked a primary source.", retryable=True))
    emit(EventType.MESSAGE_SENT, "Critic requested stronger evidence from Scout.", agent_id="critic", target_agent_id="scout", metadata={"message": "Find a primary source for mortality risk."})
    emit(EventType.RETRYING, "Scout used one retry to search again.", agent_id="scout", task_id="task-search", metadata={"attempt": 2, "retry_budget_remaining": 0})
    emit(EventType.TOOL_STARTED, "Scout started a focused second search.", agent_id="scout", task_id="task-search", tool=ToolInfo("web_search", "call-search-002", "urban heat mortality primary study"))
    emit(EventType.TOOL_COMPLETED, "The second search found a primary study.", agent_id="scout", task_id="task-search", tool=ToolInfo("web_search", "call-search-002", output_summary="1 primary study accepted"))
    evidence = ArtifactInfo("artifact-evidence", "evidence_bundle", "Accepted urban heat evidence")
    emit(EventType.ARTIFACT_CREATED, "Scout created the accepted evidence bundle.", agent_id="scout", task_id="task-search", artifact=evidence)
    emit(EventType.TASK_COMPLETED, "Scout completed the evidence search.", agent_id="scout", task_id="task-search")
    emit(EventType.AGENT_COMPLETED, "Scout finished its assigned work.", agent_id="scout")
    emit(EventType.TASK_COMPLETED, "Critic accepted the revised evidence.", agent_id="critic", task_id="task-review")
    emit(EventType.HANDOFF_STARTED, "Critic handed accepted evidence to Writer.", agent_id="critic", target_agent_id="writer", artifact=evidence)
    emit(EventType.AGENT_COMPLETED, "Critic finished its assigned work.", agent_id="critic")

    emit(EventType.TASK_STARTED, "Writer began drafting the answer.", agent_id="writer", task_id="task-write")
    answer = ArtifactInfo("artifact-answer", "answer", "Urban heat and city health")
    emit(EventType.ARTIFACT_CREATED, "Writer created the final answer.", agent_id="writer", task_id="task-write", artifact=answer)
    emit(EventType.TASK_COMPLETED, "Writer completed the final answer.", agent_id="writer", task_id="task-write")
    emit(EventType.AGENT_COMPLETED, "Writer finished its assigned work.", agent_id="writer")
    emit(EventType.RUN_COMPLETED, "Research run completed successfully.", metadata={"status": "succeeded", "result_artifact_id": answer.artifact_id})
    return events


DEMO_EVENTS = create_demo_events()
