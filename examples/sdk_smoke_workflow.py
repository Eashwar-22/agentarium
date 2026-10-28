"""Exercise Agentarium with a real Agents SDK run and a local model.

Run from the repository root:
    python -m examples.sdk_smoke_workflow

This uses the SDK runner, one function tool, and a deterministic model. It makes
no network or paid API calls. The recording is written to a separate local file.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agents import Agent, RunConfig, function_tool
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from agentarium import CapturePolicy, observe_openai
from agentarium.events import AgentEvent, EventType, validate_event_sequence


EVENT_PATH = Path('.agentarium/sdk-smoke.jsonl')


@function_tool
def inspect_release_checks(component: str) -> str:
    """Check that the dashboard files and browser test are present locally."""
    root = Path(__file__).resolve().parents[1]
    return json.dumps({
        'component': component,
        'files': {
            'dashboard_html': (root / 'agentarium/static/index.html').is_file(),
            'dashboard_css': (root / 'agentarium/static/styles.css').is_file(),
            'browser_test': (root / 'tests/browser/dashboard.cjs').is_file(),
        },
        'source': 'local filesystem',
    })


class ScriptedModel(Model):
    """A deterministic model response sequence for an offline SDK smoke run."""

    def __init__(self) -> None:
        self.calls = 0

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, *, previous_response_id,
                           conversation_id, prompt) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            output = [ResponseFunctionToolCall(
                arguments=json.dumps({'component': 'dashboard'}),
                call_id='sdk-smoke-tool-1', name='inspect_release_checks',
                type='function_call',
            )]
        else:
            output = [ResponseOutputMessage(
                id='sdk-smoke-answer-1', role='assistant', status='completed',
                type='message', content=[ResponseOutputText(
                    annotations=[], type='output_text',
                    text='The dashboard files and browser test are present. Agentarium recorded this SDK tool call and result.',
                )],
            )]
        return ModelResponse(
            output=output, usage=Usage(requests=1, input_tokens=12,
                                       output_tokens=18, total_tokens=30),
            response_id=f'sdk-smoke-response-{self.calls}',
        )

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError('This smoke run uses Runner.run, not streaming.')
        yield  # Keep this method an async iterator for the SDK interface.


async def main() -> None:
    model = ScriptedModel()
    agent = Agent(
        name='Release reviewer',
        instructions='Use inspect_release_checks, then give one short conclusion.',
        tools=[inspect_release_checks],
        model=model,
    )
    async with observe_openai(
        'Check the dashboard release workflow',
        str(EVENT_PATH),
        capture_policy=CapturePolicy(full_payloads=True),
    ) as observed:
        result = await observed.run(
            agent, 'Check the dashboard release workflow.',
            max_turns=3, run_config=RunConfig(tracing_disabled=True),
        )

    events = [AgentEvent.from_json(line) for line in EVENT_PATH.read_text().splitlines()]
    validate_event_sequence(events)
    kinds = {event.type for event in events}
    required = {EventType.MODEL_STARTED, EventType.MODEL_COMPLETED,
                EventType.TOOL_STARTED, EventType.TOOL_COMPLETED,
                EventType.ARTIFACT_CREATED, EventType.RUN_COMPLETED}
    missing = required - kinds
    if missing or model.calls != 2:
        raise RuntimeError(f'Incomplete SDK smoke trace: {sorted(kind.value for kind in missing)}')
    tool_result = next(event for event in events if event.type is EventType.TOOL_COMPLETED)
    observed_checks = json.loads(tool_result.metadata['tool_output_full'])['files']
    if not all(observed_checks.values()):
        raise RuntimeError(f'Local dashboard files are missing: {observed_checks}')
    print(result.final_output)
    print(f'Validated {len(events)} events in {EVENT_PATH}.')
    print('To view this trace: AGENTARIUM_EVENT_FILE=.agentarium/sdk-smoke.jsonl agentarium-dashboard --port 8001')


if __name__ == '__main__':
    asyncio.run(main())
