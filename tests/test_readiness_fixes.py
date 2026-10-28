import asyncio
import json
import os
import stat
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch, AsyncMock

from agents import Agent
from agentarium import CapturePolicy, run_sync, observe_openai
from agentarium.core import EventRecorder
from agentarium.events import SourceInfo
from agentarium.openai_agents import AgentariumRunHooks


class ReadinessFixTests(unittest.TestCase):
    def test_callback_serialization_failure_does_not_escape(self):
        async def exercise(path):
            recorder = EventRecorder('test', path, capture_policy=CapturePolicy(full_payloads=True))
            recorder.start()
            hooks = AgentariumRunHooks(recorder)
            agent = Agent(name='A')
            await hooks.on_agent_start(None, agent)
            circular = {}
            circular['self'] = circular
            with warnings.catch_warnings(record=True) as observed:
                warnings.simplefilter('always')
                await hooks.on_tool_end(None, agent, type('Tool', (), {'name': 'lookup'})(), circular)
                await hooks.on_agent_end(None, agent, circular)
            self.assertIsNotNone(recorder.recording_error)
            self.assertEqual(len(observed), 1)
            recorder.finish()
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(exercise(Path(tmp)/'events.jsonl'))

    def test_successful_result_survives_final_recording_failure(self):
        result = object()
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            with patch('agentarium.openai.Runner.run_sync', return_value=result), patch.object(EventRecorder, 'finish', side_effect=ValueError('cannot finalize')):
                actual = run_sync(Agent(name='A'), 'input', event_path=str(Path(tmp)/'events.jsonl'), show_dashboard=False)
            self.assertIs(actual, result)
            self.assertEqual(len(observed), 1)

    def test_private_workflow_policy_covers_file_and_export(self):
        token = 'synthetic-access-token'
        address = 'customer@example.com'
        policy = CapturePolicy(
            redact_values=(token,),
            redactor=lambda text: text.replace(address, '[EMAIL]'),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'events.jsonl'
            recorder = EventRecorder('Research for '+address, path, capture_policy=policy)
            recorder.start()
            aid = recorder.discover_agent('a', 'Researcher')
            recorder.start_task(aid, 'Researcher', activity='Look up '+address)
            recorder.record_tool_end(aid, 'search', 'call-1', 'Found '+address,
                sources=(SourceInfo('Source', 'https://example.com/report?key='+token),))
            recorder.record_artifact(aid, 'answer', 'Result', preview='Sent to '+address,
                content='Full private payload '+token)
            recorder.finish()
            exported = json.dumps([event.to_dict() for event in recorder.events])
            for saved in (path.read_text(), exported):
                self.assertNotIn(token, saved)
                self.assertNotIn(address, saved)
                self.assertNotIn('Full private payload', saved)

    def test_full_payloads_require_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AGENTARIUM_CAPTURE_FULL', None)
            recorder = EventRecorder('private summary', Path(tmp)/'events.jsonl')
            recorder.start()
            aid = recorder.discover_agent('a', 'A')
            recorder.start_task(aid, 'A', activity='summary', activity_full='private full payload')
            recorder.finish()
            self.assertNotIn('private full payload', recorder.event_path.read_text())
            task = next(event for event in recorder.events if event.type.value == 'task_started')
            self.assertNotIn('activity_full', task.metadata)

    def test_concurrent_recorder_cannot_replace_active_trace(self):
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            path = Path(tmp)/'events.jsonl'
            first = EventRecorder('first', path)
            first.start()
            before = path.read_text()
            second = EventRecorder('second', path)
            second.start()
            second.finish()
            self.assertEqual(path.read_text(), before)
            self.assertIsNotNone(second.recording_error)
            self.assertEqual(len(observed), 1)
            first.finish()
            third = EventRecorder('third', path)
            third.start()
            third.finish()
            self.assertIn('third', path.read_text())

    def test_each_model_call_records_its_actual_context(self):
        async def exercise(path):
            recorder = EventRecorder('test', path, capture_policy=CapturePolicy(full_payloads=True))
            recorder.start()
            hooks = AgentariumRunHooks(recorder)
            agent = Agent(name='A', instructions='Test')
            hooks.set_activity(agent, 'Original request')
            await hooks.on_agent_start(None, agent)
            first = [{'role': 'user', 'content': 'Original request'}]
            second = first + [{'type': 'function_call_output', 'call_id': 'x', 'output': 'New evidence'}]
            await hooks.on_llm_start(None, agent, 'Instructions', first)
            await hooks.on_llm_start(None, agent, 'Instructions', second)
            events = [e for e in recorder.events if e.type.value == 'model_started']
            self.assertEqual(json.loads(events[0].metadata['model_input_full'])['input_items'], first)
            self.assertEqual(json.loads(events[1].metadata['model_input_full'])['input_items'], second)
            self.assertEqual(events[1].metadata['activity_full'], 'Original request')
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(exercise(Path(tmp)/'events.jsonl'))

    def test_disk_failure_keeps_a_successful_result(self):
        result = object()
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            with patch.object(Path, 'open', side_effect=OSError('store unavailable')), patch('agentarium.openai.load_env_file', return_value=False), patch('agentarium.openai.Runner.run_sync', return_value=result):
                actual = run_sync(Agent(name='A'), 'input', event_path=str(Path(tmp)/'events.jsonl'), show_dashboard=False)
            self.assertIs(actual, result)
            self.assertEqual(len(observed), 1)

    def test_secondary_recording_error_preserves_original_sync_exception(self):
        original = ValueError('original failure')
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with patch('agentarium.openai.Runner.run_sync', side_effect=original), patch.object(EventRecorder, 'record_error', side_effect=OSError('secondary failure')):
                with self.assertRaises(ValueError) as caught:
                    run_sync(Agent(name='A'), 'input', event_path=str(Path(tmp)/'events.jsonl'), show_dashboard=False)
            self.assertIs(caught.exception, original)

    def test_secondary_recording_error_preserves_original_async_exception(self):
        async def exercise(path):
            original = ValueError('original failure')
            with patch('agentarium.openai_agents.Runner.run', new=AsyncMock(side_effect=original)), patch.object(EventRecorder, 'record_error', side_effect=OSError('secondary')):
                with self.assertRaises(ValueError) as caught:
                    async with observe_openai('test', str(path)) as observed:
                        await observed.run(Agent(name='A'), 'input')
                self.assertIs(caught.exception, original)
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings():
            warnings.simplefilter('ignore')
            asyncio.run(exercise(Path(tmp)/'events.jsonl'))

    def test_capture_redacts_full_payloads_previews_and_memory(self):
        secret = 'synthetic-private-value'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'events.jsonl'
            recorder = EventRecorder('request '+secret, path, capture_policy=CapturePolicy(full_payloads=True, redact_values=(secret,)))
            recorder.start()
            aid = recorder.discover_agent('a','A')
            recorder.start_task(aid, 'A', activity=secret, activity_full=secret)
            recorder.record_tool_start(aid,'lookup','x',secret,input_full=json.dumps({'api_key': secret,'query':'safe'}))
            recorder.record_artifact(aid,'answer','Output',preview=secret,content=json.dumps({'authorization':secret,'answer':'safe'}))
            recorder.finish()
            self.assertNotIn(secret, path.read_text())
            self.assertNotIn(secret, str([e.to_dict() for e in recorder.events]))
            self.assertIn('safe', path.read_text())
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)

    def test_capture_can_disable_full_fields_and_redact_custom_text(self):
        policy = CapturePolicy(full_payloads=False, redactor=lambda text:text.replace('customer@example.com','[EMAIL]'))
        with tempfile.TemporaryDirectory() as tmp:
            recorder=EventRecorder('test',Path(tmp)/'events.jsonl',capture_policy=policy)
            recorder.start()
            aid=recorder.discover_agent('a','A')
            recorder.start_task(aid,'A','customer@example.com','full payload')
            event=recorder.events[-1]
            self.assertNotIn('activity_full',event.metadata)
            self.assertEqual(event.metadata['activity'],'[EMAIL]')

    def test_redaction_failure_does_not_persist_unsanitized_content(self):
        def broken(_):
            raise ValueError('bad policy')
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings():
            warnings.simplefilter('ignore')
            path=Path(tmp)/'events.jsonl'
            recorder=EventRecorder('synthetic secret',path,capture_policy=CapturePolicy(redactor=broken))
            recorder.start()
            self.assertEqual(path.read_text(),'')
            self.assertEqual(recorder.events,[])
            self.assertIsNotNone(recorder.recording_error)
