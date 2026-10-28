import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agents import Agent
from agentarium import CapturePolicy
from agentarium.core import EventRecorder
from agentarium.openai_agents import AgentariumRunHooks, _recorded_content


class FullPayloadTests(unittest.TestCase):
    def test_long_task_tool_and_artifact_payloads_survive_recording(self):
        text = 'recorded data ' * 1000
        async def exercise(path):
            recorder = EventRecorder('payload test', path, capture_policy=CapturePolicy(full_payloads=True))
            recorder.start()
            hooks = AgentariumRunHooks(recorder)
            agent = Agent(name='Inspector', instructions='Inspect data.')
            hooks.set_activity(agent, text)
            await hooks.on_agent_start(None, agent)
            context = SimpleNamespace(tool_call_id='call-1', tool_arguments=json.dumps({'input': text}))
            tool = SimpleNamespace(name='lookup', description='Read the data.')
            await hooks.on_tool_start(context, agent, tool)
            await hooks.on_tool_end(context, agent, tool, text)
            await hooks.on_agent_end(None, agent, text)
            recorder.finish()
            return [json.loads(line) for line in path.read_text().splitlines()]

        with tempfile.TemporaryDirectory() as directory:
            events = asyncio.run(exercise(Path(directory) / 'events.jsonl'))
        by_type = {event['type']: event for event in events}
        self.assertEqual(by_type['task_started']['metadata']['activity_full'], text)
        self.assertEqual(json.loads(by_type['tool_started']['metadata']['tool_input_full'])['input'], text)
        self.assertEqual(by_type['tool_completed']['metadata']['tool_output_full'], text)
        self.assertEqual(by_type['artifact_created']['metadata']['full_output'], text)

    def test_structured_input_remains_json(self):
        payload = [{'role': 'user', 'content': 'hello'}]
        self.assertEqual(json.loads(_recorded_content(payload)), payload)
