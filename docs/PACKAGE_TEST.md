# Test Agentarium from another project

## Install once

From the Agentarium repository root, install the package in editable mode:

```bash
python -m pip install -e .
```

## Prepare a different project folder

In the project you want to observe, keep a local `.env` with its own
`OPENAI_API_KEY`. Agentarium reads this file automatically; do not commit it.

Replace the normal OpenAI SDK runner import and call:

```python
from agents import Agent
from agentarium.openai import run_sync

agent = Agent(name="Assistant", instructions="You are a helpful assistant")

result = run_sync(agent, "Write a haiku about recursion in programming.")
print(result.final_output)
```

`run_sync` returns the normal OpenAI Agents SDK result. It also writes an
event stream to that project's `.agentarium/events.jsonl` file.

## Watch the run

Run the file from the **other** project folder:

```bash
python your_agent_file.py
```

`run_sync(...)` automatically starts a local Agentarium dashboard and opens it
in your default browser. It normally uses `http://127.0.0.1:8765/`; if that
port is busy, it selects the next available local port.

If a developer wants events but no browser window, they can opt out:

```python
result = run_sync(agent, prompt, show_dashboard=False)
```

For existing asynchronous code, use:

```python
from agentarium.openai import run

result = await run(agent, prompt)
```

This first package version supports one wrapped runner call at a time. The
larger examples in this repository still use `observe_openai(...)` when they
need manual fan-out, handoffs, or parallel branches.
