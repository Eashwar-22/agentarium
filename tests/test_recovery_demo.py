import json
import tempfile
import unittest
from pathlib import Path

from agentarium.core import EventRecorder
from agentarium.events import AgentEvent, EventType, validate_event_sequence
from examples.recovery_demo_workflow import RecoveryRuntime


class RecoveryDemoTests(unittest.TestCase):
    def test_local_lookup_fails_twice_then_recovers(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "events.jsonl"
            recorder = EventRecorder("Recovery test", path)
            recorder.start()
            agent_id = recorder.discover_agent("scout", "Recovery Scout")
            recorder.start_task(agent_id, "Recovery Scout")
            runtime = RecoveryRuntime(recorder, agent_id)

            first = json.loads(runtime.lookup("test topic"))
            second = json.loads(runtime.lookup("test topic"))
            third = json.loads(runtime.lookup("test topic"))
            recorder.complete_task(agent_id, "Recovery Scout")
            recorder.finish()
            events = [
                AgentEvent.from_json(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertFalse(first["ok"])
        self.assertFalse(second["ok"])
        self.assertTrue(third["ok"])
        self.assertEqual([event.type for event in events].count(EventType.ERROR), 2)
        self.assertEqual([event.type for event in events].count(EventType.RETRYING), 2)
        validate_event_sequence(events)


if __name__ == "__main__":
    unittest.main()
