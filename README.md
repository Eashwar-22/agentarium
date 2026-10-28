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

To test the real Agents SDK runner and Agentarium adapter without an API key:

```bash
python -m examples.sdk_smoke_workflow
AGENTARIUM_EVENT_FILE=.agentarium/sdk-smoke.jsonl agentarium-dashboard --port 8001
```

Open `http://127.0.0.1:8001/` to inspect the recorded model calls, tool call,
tool result, and final output. The script uses a deterministic local model and
checks its 13-event trace. It makes no paid calls.

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
- A run overview with current work, recorded errors and retries, saved outputs,
  source links, and measured usage
- A chronological trace with agent/action filters, search, and JSON export

The overview shows what is still open and which results are available. Open
**Trace** to inspect actions in order. Selecting an action opens its recorded
input and output in a scrollable dialog. Full payloads are used when present;
older recordings that contain only previews are labelled accordingly. No model
calls are made to generate dashboard descriptions or scores.

Live events display as they arrive. **Pause display** freezes the view while
recording continues. **Replay** plays the captured run for inspection; it does
not execute the workflow or make paid API calls. **Return to live** catches up
with the latest received events.

The event format is documented in
[docs/EVENT_SCHEMA.md](docs/EVENT_SCHEMA.md).

## Recording controls

Full payload capture is off by default. The recording still includes task
summaries, output previews, errors, and source links, which may contain private
data. To inspect current model input items, observed system instructions, full
tool arguments/results, and saved artifacts, opt in for that run. Model-call
inputs are shown separately from the original task intent.

Configure capture for a run:

```python
from agentarium import CapturePolicy, run_sync

policy = CapturePolicy(
    full_payloads=True,
    redact_values=("an-exact-secret-to-remove",),
    redactor=lambda text: text.replace("customer@example.com", "[EMAIL]"),
)
result = run_sync(agent, "Your request", capture_policy=policy)
```

`capture_policy` is also accepted by `run()` and `observe_openai()`. Credential
fields such as `api_key`, `password`, and `authorization` in structured data are
redacted by default. `redact_values` handles known secrets in free text, including
previews. Use a deterministic, idempotent `redactor` for application-specific
private data. These controls do not detect every kind of secret automatically.

For a workflow with private data, name the values that must be removed from
summaries, source URLs, and exported JSON as well as full payloads:

```python
policy = CapturePolicy(
    redact_values=(customer_token,),
    redactor=lambda text: text.replace(customer_email, "[EMAIL]"),
)
result = run_sync(agent, request, capture_policy=policy)
```

Review the recorded JSONL file before sharing an export. The redactor receives
each recorded string; it does not automatically discover other private values.

Set `AGENTARIUM_CAPTURE_FULL=1` to opt in through the environment, or pass
`CapturePolicy(full_payloads=True)`. Summaries remain recorded and still need
appropriate redaction. A redaction failure disables recording rather than
persisting unsanitized events. On supported systems new recordings are restricted
to the file owner (`0600`).

The default file holds the latest run and is replaced when a new recorder starts.
An active recorder holds a companion `.lock` file; a second recorder using the
same event path warns and skips its recording instead of replacing the first.
Use a different `event_path` for each concurrent workflow to record both runs.
Stop the workflow and delete the JSONL file when you
no longer need its contents; remove exported copies separately. The dashboard
binds to localhost and has no public sharing or access-control service.

An event-file write failure emits one warning and disables further disk writes;
the workflow continues. Original workflow results and exceptions are preserved.
Such a recording may be incomplete and should not be used as an audit record.

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

Run the browser regression suite (no API keys or paid calls):

```bash
npm ci
npm run test:browser
```

On macOS the tests use the installed Google Chrome. On other platforms Puppeteer's
downloaded Chrome is used; set `CHROME_PATH` to use an existing Chrome binary.
The suite checks full-payload dialogs, filtering, pause/resume, final-result
selection, themes, mobile overflow, pagination, and returning from replay to live.

Run the synthetic large-recording checks:

```bash
node tools/benchmark_run_view.cjs
python -m tools.benchmark_event_tail
```

These check a 10,000-event recording with 4 KB payloads, incremental reads, and
zero file-content reads during 100 idle polls. Local performance targets are
under 1 second for the frontend data model and under 10 seconds to read/parse the
file. This is the measured local workload target, about a 44 MB recording.
The benchmark also checks frontend heap below 256 MiB and file-reader peak
allocation below 128 MiB. Larger recordings and individual full payloads have
no enforced memory cap. These are development checks, not throughput guarantees
for every machine.

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

Live demo: https://agentarium-five.vercel.app/

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FEashwar-22%2Fagentarium)

1. Import this GitHub repository at [vercel.com/new](https://vercel.com/new).
2. Keep the default project settings.
3. Click **Deploy**.

Vercel serves the existing FastAPI dashboard and uses `vercel.json` to route
`/events` to the sample run. The local Python adapter continues to use real
events.
