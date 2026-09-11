"""Standard-library tests for the Agentarium Stage 2 event contract."""

from dataclasses import replace
from datetime import timedelta
import json
import unittest

from agentarium.events import (
    AgentEvent,
    DEMO_EVENTS,
    EventType,
    SCHEMA_VERSION,
    SourceInfo,
    ToolInfo,
    validate_event,
    validate_event_sequence,
)


class AgentEventTests(unittest.TestCase):
    def test_demo_is_a_valid_complete_run(self) -> None:
        validate_event_sequence(DEMO_EVENTS)

    def test_demo_covers_every_event_type(self) -> None:
        self.assertEqual({event.type for event in DEMO_EVENTS}, set(EventType))

    def test_json_round_trip_preserves_each_event(self) -> None:
        for event in DEMO_EVENTS:
            self.assertEqual(AgentEvent.from_json(event.to_json()), event)

    def test_wire_format_is_json_compatible(self) -> None:
        encoded = json.dumps([event.to_dict() for event in DEMO_EVENTS])
        self.assertIn(SCHEMA_VERSION, encoded)

    def test_previous_schema_events_remain_readable(self) -> None:
        old_event = replace(DEMO_EVENTS[0], schema_version="0.1")
        self.assertEqual(AgentEvent.from_json(old_event.to_json()), old_event)

    def test_tool_sources_and_artifact_preview_round_trip(self) -> None:
        tool_event = next(
            event for event in DEMO_EVENTS if event.type == EventType.TOOL_COMPLETED
        )
        enriched_tool = replace(
            tool_event,
            tool=ToolInfo(
                name=tool_event.tool.name,
                call_id=tool_event.tool.call_id,
                output_summary="One source found.",
                sources=(
                    SourceInfo(
                        title="Example source",
                        url="https://example.com/report",
                        snippet="Short evidence snippet.",
                    ),
                ),
            ),
        )
        self.assertEqual(AgentEvent.from_json(enriched_tool.to_json()), enriched_tool)

        artifact_event = next(
            event for event in DEMO_EVENTS if event.type == EventType.ARTIFACT_CREATED
        )
        enriched_artifact = replace(
            artifact_event,
            artifact=replace(artifact_event.artifact, preview="Short artifact preview."),
        )
        self.assertEqual(AgentEvent.from_json(enriched_artifact.to_json()), enriched_artifact)

    def test_duplicate_event_id_is_rejected(self) -> None:
        broken = list(DEMO_EVENTS)
        broken[2] = replace(broken[2], event_id=broken[1].event_id)
        with self.assertRaisesRegex(ValueError, "event_id.*unique"):
            validate_event_sequence(broken)

    def test_sequence_gap_is_rejected(self) -> None:
        broken = list(DEMO_EVENTS)
        broken[3] = replace(broken[3], sequence=99)
        with self.assertRaisesRegex(ValueError, "contiguous"):
            validate_event_sequence(broken)

    def test_backward_timestamp_is_rejected(self) -> None:
        broken = list(DEMO_EVENTS)
        broken[2] = replace(
            broken[2], timestamp=broken[1].timestamp - timedelta(seconds=1)
        )
        with self.assertRaisesRegex(ValueError, "backward"):
            validate_event_sequence(broken)

    def test_wrong_run_boundary_is_rejected(self) -> None:
        broken = list(DEMO_EVENTS)
        broken[0] = replace(
            broken[0], type=EventType.AGENT_SPAWNED, agent_id="extra"
        )
        with self.assertRaisesRegex(ValueError, "first event"):
            validate_event_sequence(broken)

    def test_missing_tool_details_are_rejected(self) -> None:
        tool_event = next(
            event for event in DEMO_EVENTS if event.type == EventType.TOOL_STARTED
        )
        with self.assertRaisesRegex(ValueError, "requires tool"):
            validate_event(replace(tool_event, tool=None))

    def test_tool_completion_without_start_is_rejected(self) -> None:
        broken = [
            event
            for event in DEMO_EVENTS
            if not (
                event.type == EventType.TOOL_STARTED
                and event.tool.call_id == "call-search-001"
            )
        ]
        broken = [
            replace(event, sequence=index)
            for index, event in enumerate(broken, start=1)
        ]
        with self.assertRaisesRegex(ValueError, "completed before tool_started"):
            validate_event_sequence(broken)

    def test_unknown_wire_field_is_rejected(self) -> None:
        raw = DEMO_EVENTS[0].to_dict()
        raw["animation"] = "flash"
        with self.assertRaisesRegex(ValueError, "Unknown event field"):
            AgentEvent.from_dict(raw)

    def test_agent_scoped_error_requires_a_spawned_agent(self) -> None:
        broken = list(DEMO_EVENTS)
        error_index = next(
            index
            for index, event in enumerate(broken)
            if event.type == EventType.ERROR
        )
        broken[error_index] = replace(broken[error_index], agent_id="unknown-agent")
        with self.assertRaisesRegex(ValueError, "before agent_spawned"):
            validate_event_sequence(broken)


if __name__ == "__main__":
    unittest.main()
