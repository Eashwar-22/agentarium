# Agentarium

Agentarium is a local visual debugger for workflows built with the OpenAI
Agents SDK. It records observable run events and shows them as a live agent
dashboard.

The dashboard answers practical questions:

- Which agent is active?
- Which tools did it call?
- Where did its sources come from?
- Which step failed or retried?
- What happened from the start of the run to the end?

Agentarium records tool activity, handoffs, errors, usage counts, artifacts,
and output summaries. It does not request or display private chain-of-thought.

## Quick start

Agentarium needs Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

Add your `OPENAI_API_KEY` to `.env`, then wrap a normal SDK run:

```python
from agents import Agent
from agentarium import run_sync

agent = Agent(
    name="Writer",
    instructions="Write one clear sentence about the given topic.",
)

result = run_sync(agent, "Why observability matters")
print(result.final_output)
```

Running this file starts the dashboard and opens it in your browser. Events are
saved locally in `.agentarium/events.jsonl`.

## Run an example

The search examples also need Tavily:

```bash
python -m pip install -e ".[examples]"
python -m examples.random_agent_chaos "why cats knock things off tables"
```

That command makes real OpenAI and Tavily API calls. More workflows are listed
in [docs/REAL_WORKFLOW.md](docs/REAL_WORKFLOW.md).

## Use the dashboard by itself

```bash
agentarium-dashboard --port 8000
```

By default, it reads `.agentarium/events.jsonl` from the current directory. Set
`AGENTARIUM_EVENT_FILE` to read a different event file.

## What gets recorded

- Agent and task lifecycle events
- Model call timing and token usage
- Tool inputs, result summaries, and source URLs
- Agent messages and handoffs
- Errors and retries
- Artifacts and output previews
- A post-run scorecard and complete run story

The event format is documented in
[docs/EVENT_SCHEMA.md](docs/EVENT_SCHEMA.md).

## Current limits

- The adapter currently targets the OpenAI Agents SDK.
- The simple `run()` and `run_sync()` helpers support one wrapped runner call at
  a time.
- Multi-agent fan-out and custom handoffs use `observe_openai()`.
- The dashboard is local and has no authentication layer.

## Development

Run the Python and browser-logic tests:

```bash
python -m unittest discover -s tests -v
node --test tests/*.js
```

Build a wheel:

```bash
python -m pip wheel --no-deps --wheel-dir dist .
```

Project layout:

```text
agentarium/         Python package and dashboard assets
examples/           Runnable agent workflows
tests/              Python and JavaScript tests
docs/               Event schema and longer guides
```

Agentarium is an early prototype. The public API and event schema may change.

## Deploy the prerecorded Vercel demo

The public demo replays fixed events. It needs no API keys and makes no OpenAI
or Tavily calls.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FEashwar-22%2Fagentarium)

1. Import this GitHub repository at [vercel.com/new](https://vercel.com/new).
2. Keep the default project settings.
3. Click **Deploy**.

Vercel uses `vercel.json` to serve the existing dashboard and `/api/events` to
stream the sample run. The local Python adapter continues to use real events.
