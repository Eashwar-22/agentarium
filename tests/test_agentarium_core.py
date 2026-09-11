import tempfile
import unittest
from pathlib import Path

from agentarium.core import EventRecorder
from agentarium.events import AgentEvent, EventType, validate_event_sequence


class EventRecorderTests(unittest.TestCase):
    def test_discovers_unknown_agents_and_writes_valid_run(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "events.jsonl"
            recorder = EventRecorder("Test question", path)
            recorder.start()
            first = recorder.discover_agent("object-one", "Research Agent")
            second = recorder.discover_agent("object-two", "Research Agent")
            recorder.start_task(first, "Research Agent")
            recorder.complete_task(first, "Research Agent")
            recorder.handoff(first, second, "Research Agent", "Research Agent")
            recorder.finish()

            events = [
                AgentEvent.from_json(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(first, "research-agent")
        self.assertEqual(second, "research-agent-2")
        self.assertEqual(
            [event.type for event in events].count(EventType.AGENT_SPAWNED), 2
        )
        validate_event_sequence(events)

    def test_records_retryable_error_and_retry_for_active_task(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "events.jsonl"
            recorder = EventRecorder("Test question", path)
            recorder.start()
            agent_id = recorder.discover_agent("object-one", "Recovery Scout")
            recorder.start_task(agent_id, "Recovery Scout")
            recorder.record_error(
                "Temporary lookup failure.",
                agent_id,
                code="temporary_lookup_failure",
                retryable=True,
            )
            recorder.record_retry(agent_id, "Recovery Scout is retrying.", attempt=2)
            recorder.complete_task(agent_id, "Recovery Scout")
            recorder.finish()
            events = [
                AgentEvent.from_json(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        error = next(event for event in events if event.type is EventType.ERROR)
        retry = next(event for event in events if event.type is EventType.RETRYING)
        self.assertTrue(error.error.retryable)
        self.assertEqual(error.error.code, "temporary_lookup_failure")
        self.assertEqual(retry.metadata["attempt"], 2)
        validate_event_sequence(events)


if __name__ == "__main__":
    unittest.main()
