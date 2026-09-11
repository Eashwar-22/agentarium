import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agents import Agent

from agentarium.core import EventRecorder
from agentarium.openai_agents import AgentariumRunHooks, OpenAIAgentsObserver
from agentarium.events import AgentEvent, EventType, validate_event_sequence


class FakeTool:
    name = "fake_search"


class FakeToolContext:
    tool_call_id = "call-001"
    tool_arguments = '{"query":"test"}'


class FakeUsage:
    input_tokens = 12
    output_tokens = 8
    total_tokens = 20


class FakeResponse:
    output = ["one"]
    usage = FakeUsage()


class OpenAIAgentsAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_translates_unknown_agent_and_tool_callbacks(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "events.jsonl"
            recorder = EventRecorder("Test question", path)
            recorder.start()
            hooks = AgentariumRunHooks(recorder)
            agent = Agent(name="Custom Researcher", instructions="Be concise.")

            hooks.set_activity(agent, "Investigate a test question")
            await hooks.on_agent_start(None, agent)
            await hooks.on_llm_start(None, agent, None, ["input"])
            await hooks.on_llm_end(None, agent, FakeResponse())
            await hooks.on_tool_start(FakeToolContext(), agent, FakeTool())
            await hooks.on_tool_end(
                FakeToolContext(),
                agent,
                FakeTool(),
                json.dumps({
                    "results": [{
                        "title": "Example result",
                        "url": "https://example.com/report",
                        "content": "Useful evidence.",
                    }],
                }),
            )
            await hooks.on_agent_end(None, agent, "final answer text")
            recorder.finish()

            events = [
                AgentEvent.from_json(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(events[1].agent_id, "custom-researcher")
        self.assertIn(EventType.MODEL_STARTED, [event.type for event in events])
        self.assertIn(EventType.MODEL_COMPLETED, [event.type for event in events])
        self.assertIn(EventType.TOOL_STARTED, [event.type for event in events])
        self.assertIn(EventType.TOOL_COMPLETED, [event.type for event in events])
        completed_tool = next(event for event in events if event.type is EventType.TOOL_COMPLETED)
        self.assertEqual(completed_tool.tool.sources[0].url, "https://example.com/report")
        artifact = next(event for event in events if event.type is EventType.ARTIFACT_CREATED)
        self.assertEqual(artifact.artifact.preview, "final answer text")
        validate_event_sequence(events)

    async def test_parallel_runs_can_skip_automatic_handoffs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "events.jsonl"
            first = Agent(name="First branch", instructions="Do one thing.")
            second = Agent(name="Second branch", instructions="Do another thing.")
            observer = OpenAIAgentsObserver("Parallel test", path)

            with patch(
                "agentarium.openai_agents.Runner.run", new=AsyncMock(return_value=object())
            ):
                async with observer:
                    observer.hooks.identify(first)
                    observer.hooks.identify(second)
                    await observer.run(first, "start")
                    await observer.run(second, "independent", handoff_from=None)

            events = [
                AgentEvent.from_json(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        handoffs = [event for event in events if event.type is EventType.HANDOFF_STARTED]
        self.assertEqual(handoffs, [])
        validate_event_sequence(events)

    async def test_observer_can_start_the_dashboard(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "events.jsonl"
            with patch("agentarium.openai_agents.start_dashboard") as dashboard:
                async with OpenAIAgentsObserver(
                    "Dashboard test", path, show_dashboard=True, dashboard_port=9012
                ):
                    pass

        dashboard.assert_called_once_with(path, port=9012, open_browser=True)


if __name__ == "__main__":
    unittest.main()
