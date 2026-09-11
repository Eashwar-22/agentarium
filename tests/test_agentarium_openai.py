import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents import Agent

from agentarium.openai import run_sync
from agentarium.openai_agents import AgentariumRunHooks
from agentarium.events import AgentEvent, EventType, validate_event_sequence


class OpenAIConvenienceTests(unittest.TestCase):
    def test_run_sync_preserves_the_sdk_result_and_writes_a_valid_run(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "events.jsonl"
            agent = Agent(name="Tiny Assistant", instructions="Be concise.")
            sdk_result = object()
            with patch(
                "agentarium.openai.Runner.run_sync", return_value=sdk_result
            ) as runner:
                result = run_sync(
                    agent, "Write one line.", event_path=str(path), show_dashboard=False
                )

            events = [
                AgentEvent.from_json(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertIs(result, sdk_result)
        self.assertIsInstance(runner.call_args.kwargs["hooks"], AgentariumRunHooks)
        self.assertEqual(events[0].type, EventType.RUN_STARTED)
        self.assertEqual(events[-1].type, EventType.RUN_COMPLETED)
        validate_event_sequence(events)

    def test_run_sync_rejects_competing_hooks(self):
        agent = Agent(name="Tiny Assistant", instructions="Be concise.")
        with self.assertRaises(ValueError):
            run_sync(agent, "Write one line.", hooks=object())

    def test_run_sync_starts_the_dashboard_by_default(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "events.jsonl"
            agent = Agent(name="Tiny Assistant", instructions="Be concise.")
            with (
                patch("agentarium.openai.Runner.run_sync", return_value=object()),
                patch("agentarium.openai.start_dashboard") as dashboard,
            ):
                run_sync(agent, "Write one line.", event_path=str(path), dashboard_port=9011)

        dashboard.assert_called_once_with(
            path,
            port=9011,
            open_browser=True,
        )


if __name__ == "__main__":
    unittest.main()
