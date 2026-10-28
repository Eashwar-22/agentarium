"""Framework-independent runtime event recorder for Agentarium."""

from __future__ import annotations

import os
import re
import warnings
try:
    import fcntl
except ImportError:  # Windows
    import msvcrt
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Hashable
from uuid import uuid4

from .capture import CapturePolicy

from .events import (
    AgentEvent,
    ArtifactInfo,
    ErrorInfo,
    EventType,
    SourceInfo,
    ToolInfo,
    validate_event,
)


def default_event_path() -> Path:
    configured = os.environ.get("AGENTARIUM_EVENT_FILE")
    return Path(configured) if configured else Path.cwd() / ".agentarium" / "events.jsonl"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "agent"


class EventRecorder:
    """Build valid Agentarium events and append them to a live JSONL stream."""

    def __init__(self, question: str, event_path: Path | str | None = None, *, capture_policy: CapturePolicy | None = None) -> None:
        self.question = question
        self.event_path = Path(event_path) if event_path else default_event_path()
        self.run_id = f"run-{uuid4().hex[:12]}"
        self.events: list[AgentEvent] = []
        self._agent_ids: dict[Hashable, str] = {}
        self._used_agent_ids: set[str] = set()
        self._active_tasks: dict[str, str] = {}
        self._task_counts: dict[str, int] = {}
        self._started = False
        self._finished = False
        self.capture_policy = capture_policy or CapturePolicy.from_env()
        self.recording_error: Exception | None = None
        self._last_artifact_id: str | None = None
        self._lock_fd: int | None = None

    def _release_file_lock(self) -> None:
        if self._lock_fd is None:
            return
        try:
            if os.name == "nt":
                os.lseek(self._lock_fd, 0, os.SEEK_SET)
                msvcrt.locking(self._lock_fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(self._lock_fd)
            self._lock_fd = None

    def _acquire_file_lock(self) -> None:
        lock_path = self.event_path.with_name(self.event_path.name + ".lock")
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if os.name == "nt":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise
        self._lock_fd = fd

    def _disable_recording(self, error: Exception) -> None:
        if self.recording_error is None:
            self.recording_error = error
            try:
                self._release_file_lock()
            except OSError:
                pass
            try:
                warnings.warn("Agentarium could not persist its recording. Workflow execution continues; the trace may be incomplete.", RuntimeWarning, stacklevel=2)
            except Warning:
                pass  # A warnings-as-errors setting must not interrupt the caller.

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        if self.recording_error is not None:
            return
        try:
            self.event_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._acquire_file_lock()
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.event_path, flags, 0o600)
            try:
                if hasattr(os, "fchmod"):
                    os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
        except OSError as exc:
            self._disable_recording(exc)
        self.emit(
            EventType.RUN_STARTED,
            "Agent workflow started.",
            metadata={"question": self.question},
        )

    def emit(self, event_type: EventType, summary: str, **details: Any) -> AgentEvent:
        if not self._started:
            raise RuntimeError("Start the Agentarium recorder before emitting events")
        if self._finished:
            raise RuntimeError("Cannot emit events after the Agentarium run has finished")

        sequence = len(self.events) + 1
        event = AgentEvent(
            run_id=self.run_id,
            event_id=f"{self.run_id}-evt-{sequence:04d}",
            sequence=sequence,
            timestamp=datetime.now(timezone.utc),
            type=event_type,
            summary=summary,
            **details,
        )
        validate_event(event)
        try:
            raw = event.to_dict()
            for field in ("summary", "metadata", "tool", "artifact", "error"):
                raw[field] = self.capture_policy.sanitize(raw[field])
            event = AgentEvent.from_dict(raw)
        except Exception as exc:
            # Fail closed: never persist an unsanitized payload.
            self._disable_recording(exc)
            return event
        self.events.append(event)
        if self.recording_error is None:
            try:
                with self.event_path.open("a", encoding="utf-8") as stream:
                    stream.write(event.to_json() + "\n")
            except OSError as exc:
                self._disable_recording(exc)
        return event

    def discover_agent(self, identity: Hashable, name: str, description: str | None = None) -> str:
        known = self._agent_ids.get(identity)
        if known:
            return known

        base = _slug(name)
        agent_id = base
        suffix = 2
        while agent_id in self._used_agent_ids:
            agent_id = f"{base}-{suffix}"
            suffix += 1

        self._agent_ids[identity] = agent_id
        self._used_agent_ids.add(agent_id)
        self.emit(
            EventType.AGENT_SPAWNED,
            f"{name} joined the run.",
            agent_id=agent_id,
            metadata={"name": name, "role": name, **({"description": description} if description else {})},
        )
        return agent_id

    def start_task(
        self, agent_id: str, name: str, activity: str | None = None, activity_full: str | None = None
    ) -> str:
        existing = self._active_tasks.get(agent_id)
        if existing:
            return existing
        count = self._task_counts.get(agent_id, 0) + 1
        self._task_counts[agent_id] = count
        task_id = f"{agent_id}-task-{count}"
        self._active_tasks[agent_id] = task_id
        summary = f"{name} started working."
        if activity:
            summary = f"{name} started: {activity}"
        self.emit(
            EventType.TASK_STARTED,
            summary,
            agent_id=agent_id,
            task_id=task_id,
            metadata={
                **({"activity": activity} if activity else {}),
                **({"activity_full": activity_full} if activity_full else {}),
            },
        )
        return task_id

    def complete_task(self, agent_id: str, name: str) -> None:
        task_id = self._active_tasks.pop(agent_id, None)
        if task_id:
            self.emit(
                EventType.TASK_COMPLETED,
                f"{name} completed its task.",
                agent_id=agent_id,
                task_id=task_id,
            )

    def active_task(self, agent_id: str) -> str | None:
        return self._active_tasks.get(agent_id)

    def handoff(self, source_id: str, target_id: str, source_name: str, target_name: str) -> None:
        self.emit(
            EventType.HANDOFF_STARTED,
            f"{source_name} handed work to {target_name}.",
            agent_id=source_id,
            target_agent_id=target_id,
        )

    def finish(self, succeeded: bool = True) -> None:
        if self._finished:
            return
        for agent_id, task_id in list(self._active_tasks.items()):
            self.emit(
                EventType.TASK_COMPLETED,
                "Agent task stopped with the run.",
                agent_id=agent_id,
                task_id=task_id,
            )
            self._active_tasks.pop(agent_id, None)
        for agent_id in self._used_agent_ids:
            self.emit(
                EventType.AGENT_COMPLETED,
                "Agent finished its assigned work.",
                agent_id=agent_id,
            )
        status = "succeeded" if succeeded else "failed"
        self.emit(
            EventType.RUN_COMPLETED,
            f"Agent workflow {status}.",
            metadata={"status": status, **({"final_artifact_id": self._last_artifact_id} if self._last_artifact_id else {})},
        )
        self._finished = True
        self._release_file_lock()

    def record_error(
        self,
        message: str,
        agent_id: str | None = None,
        *,
        code: str = "workflow_error",
        retryable: bool = False,
    ) -> None:
        self.emit(
            EventType.ERROR,
            "The workflow hit an error.",
            agent_id=agent_id,
            task_id=self.active_task(agent_id) if agent_id else None,
            error=ErrorInfo(code=code, message=message, retryable=retryable),
        )

    def record_retry(
        self,
        agent_id: str,
        message: str,
        *,
        attempt: int | None = None,
    ) -> None:
        """Record an observable retry for an agent with active work."""

        task_id = self.active_task(agent_id)
        if not task_id:
            raise RuntimeError("Cannot record a retry without an active task")
        metadata = {"attempt": attempt} if attempt is not None else {}
        self.emit(
            EventType.RETRYING,
            message,
            agent_id=agent_id,
            task_id=task_id,
            metadata=metadata,
        )

    def record_tool_start(
        self,
        agent_id: str,
        tool_name: str,
        call_id: str,
        input_summary: str | None,
        description: str | None = None,
        input_full: str | None = None,
    ) -> None:
        self.emit(
            EventType.TOOL_STARTED,
            f"{agent_id} started {tool_name}.",
            agent_id=agent_id,
            task_id=self.active_task(agent_id),
            tool=ToolInfo(tool_name, call_id, input_summary=input_summary),
            metadata={
                **({"tool_description": description} if description else {}),
                **({"tool_input_full": input_full} if input_full else {}),
            },
        )

    def record_model_start(
        self,
        agent_id: str,
        agent_name: str,
        activity: str | None,
        input_items: int,
        model: str,
        activity_full: str | None = None,
        model_input_full: str | None = None,
    ) -> None:
        summary = f"{agent_name} is asking the language model what to do next."
        if activity:
            summary = f"{agent_name} is working on: {activity}"
        self.emit(
            EventType.MODEL_STARTED,
            summary,
            agent_id=agent_id,
            task_id=self.active_task(agent_id),
            metadata={
                "activity": activity,
                "input_items": input_items,
                "model": model,
                **({"activity_full": activity_full} if activity_full else {}),
                **({"model_input_full": model_input_full} if model_input_full is not None else {}),
            },
        )

    def record_model_end(
        self,
        agent_id: str,
        agent_name: str,
        activity: str | None,
        output_items: int,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        output_full: str | None = None,
    ) -> None:
        self.emit(
            EventType.MODEL_COMPLETED,
            f"{agent_name} received {output_items} observable model output item(s).",
            agent_id=agent_id,
            task_id=self.active_task(agent_id),
            metadata={
                "output_items": output_items,
                "activity": activity,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                **({"model_output_full": output_full} if output_full else {}),
            },
        )

    def record_tool_end(
        self,
        agent_id: str,
        tool_name: str,
        call_id: str,
        output_summary: str | None,
        sources: tuple[SourceInfo, ...] = (),
        output_full: str | None = None,
    ) -> None:
        self.emit(
            EventType.TOOL_COMPLETED,
            f"{agent_id} completed {tool_name}.",
            agent_id=agent_id,
            task_id=self.active_task(agent_id),
            tool=ToolInfo(
                tool_name,
                call_id,
                output_summary=output_summary,
                sources=sources,
            ),
            metadata={"tool_output_full": output_full} if output_full else {},
        )

    def record_artifact(
        self,
        agent_id: str,
        kind: str,
        title: str,
        preview: str | None = None,
        content: str | None = None,
    ) -> None:
        artifact_id = f"artifact-{uuid4().hex[:10]}"
        self._last_artifact_id = artifact_id
        self.emit(
            EventType.ARTIFACT_CREATED,
            f"{agent_id} created {title}.",
            agent_id=agent_id,
            task_id=self.active_task(agent_id),
            artifact=ArtifactInfo(
                artifact_id=artifact_id,
                kind=kind,
                title=title,
                preview=preview,
            ),
            metadata={"full_output": content} if content is not None else {},
        )
