# Real research workflow

This real workflow is now wrapped by the first Agentarium adapter. Agent names
are discovered while they run; Agentarium does not contain a fixed agent list.

## Flow

```text
question
   |
Planner -> Scout -> Critic -> Writer -> answer
              ^        |
              | reject |
              +--------+  (maximum one retry)
```

- **Planner:** creates two search queries and success criteria.
- **Scout:** is the only agent with the Tavily search tool.
- **Critic:** accepts the evidence or asks for one focused retry.
- **Writer:** answers from the collected evidence and cites its URLs.

Each stage prints its output in the terminal. The wrapper also writes normalized
live events to `.agentarium/events.jsonl`, which the local server streams to the
browser.

## Setup

Use the same Python environment where you want to run the demo. Put your keys
in the existing `.env` file; every workflow loads it automatically. You do not
need to run `set -a`, `source .env`, or `set +a` again. Shell variables still
override `.env` values if you deliberately set them.

```bash
python -m pip install -r requirements-workflow.txt
```

Do not commit the `.env` file.

## Run

Use one terminal. The workflow automatically starts the local dashboard and
opens it in your browser. Activate the clean environment once if this is a new
terminal; the older `aiagent` environment has unrelated package conflicts.

```bash
conda activate agentarium-demo
python -m examples.research_workflow
```

The browser receives the real events while the agents run.

The UI buffers events so fast workflows remain readable. Use **Pause** and the
speed selector to control playback. The **Happening now** card describes one
action in plain language. Click an avatar to inspect it, or open **View all body
signals** for the complete Mind, Hands, Core, Artifact, and Progress history.
Model activity is shown as safe task summaries and usage counts, never private
chain-of-thought.

Hover a body region for a compact explanation of its color and state. Mind
shows model activity, Hands shows tool calls, Core shows errors and retries,
Artifact shows saved outputs, and Progress shows task completion. These cards
are computed from the same local event stream; they never make an LLM call.

Two events add brief white activity cues above the avatar without covering it:
`thinking…` appears above the head when a model call starts, and a tool name
such as `find_local_places` appears above the active hand. Each cue fades in,
floats slightly, and fades out. Artifacts, handoffs, and messages do not add
avatar text.

The **Developer trace** is reconstructed locally from the same appended event
file. It pairs task, model, and tool start/completion events to show durations,
inputs, outputs, and token counts. When the run completes, **How the work moved**
shows every discovered agent, tool, artifact, message, and handoff. These views
do not call an LLM or any external API.

The **Post-run scorecard** turns the same events into an execution score, task
progress, tool success, token usage, errors, retries, a bottleneck candidate,
and exact repeated-call warnings. Cost appears only when an adapter reports it.
The execution score measures workflow mechanics, not factual answer quality.

The **Run story** gives each discovered agent a readable chapter plus one full
start-to-finish timeline. It shows recorded task intent, model activity and
usage, tool inputs and result summaries, outputs, handoffs, errors, retries,
and source links. The adapter extracts source URLs from structured tool results
and saves short output previews using local code only. It never makes an extra
LLM call and never presents private chain-of-thought as observable data.

To use a different question:

```bash
python -m examples.research_workflow "What are the main benefits and risks of AI tutors?"
```

This makes real OpenAI and Tavily API calls, so it can use API credits.

## Test a different codebase shape

`examples/travel_workflow.py` is a separate workflow with no frontend configuration. It
uses four different runtime names and two different tools:

```text
Request Router
    -> Weather Specialist (check_destination_weather)
    -> Travel Advisor (find_local_places)
    -> Itinerary Composer
```

Run this from the same terminal:

```bash
python -m examples.travel_workflow
```

You can also supply a different request:

```bash
python -m examples.travel_workflow "Plan two winter days in Vienna for a solo art lover"
```

The UI should discover all four names and both tools without any frontend
changes. The live developer trace grows during the run, and the completed map
appears after the final event. Running this workflow makes real OpenAI and
Tavily calls; replaying its saved events does not.

## Stress-test a larger workflow

`examples/complex_research_workflow.py` is a separate six-agent workflow designed to
test a larger Agentarium run:

```text
Intake Analyst -> Research Planner -> Web Researcher -> Evidence Analyst
    -> Draft Writer -> Quality Reviewer
                         ^                |
                         +--- revision ---+
```

It uses two tools (`search_evidence` and `score_source_domains`), messages,
handoffs, artifacts, and an optional single revision pass. The browser learns
every agent and tool name from events; none are added to the frontend.

Run this from the same terminal:

```bash
python -m examples.complex_research_workflow
```

You can give it your own question:

```bash
python -m examples.complex_research_workflow "What should a startup check before using AI agents for customer support?"
```

This is the most expensive local demo so far because it makes multiple OpenAI
and Tavily calls. Replaying its saved events is free.

## Test real parallel work

`examples/parallel_due_diligence_workflow.py` is the largest example. It has eight
agents, three Tavily tools, and a real fan-out/fan-in shape:

```text
Decision Coordinator
  ├─ Market Researcher ───┐
  ├─ Risk Researcher ─────┼─> Evidence Synthesizer -> Decision Architect
  └─ Technical Researcher ┘                         -> Decision Reviewer
                                                    -> Final Brief Writer
```

The three researchers use `asyncio.gather`, so they run at the same time. The
wrapper records those as independent branches—there is no made-up handoff from
one specialist to another.

Run this from the same terminal:

```bash
python -m examples.parallel_due_diligence_workflow
```

For your own decision question:

```bash
python -m examples.parallel_due_diligence_workflow "Should a small clinic use an AI appointment assistant?"
```

This makes real OpenAI and three Tavily calls, so it uses API credits. The
browser should show the three specialist avatars changing state in an
interleaved order, then all three handoffs converging on Evidence Synthesizer.

## Test a controlled recovery

`examples/recovery_demo_workflow.py` is the failure demo for the pitch. Its local
catalog tool reports two retryable failures, emits real `error` and `retrying`
events, then succeeds on the third attempt. A second agent writes a short
recovery report.

```text
Recovery Scout -> local lookup fails -> retry -> fails -> retry -> succeeds
    -> Recovery Reporter
```

It uses OpenAI but no Tavily calls. Run it from the same terminal:

```bash
python -m examples.recovery_demo_workflow
```

## Test a playful research-and-debunk run

`examples/random_agent_chaos.py` is a three-agent workflow that makes the Run story easy
to inspect:

```text
Researcher -> Conspiracist -> Debunker
```

The Researcher uses Tavily and records its source URLs. The Conspiracist turns
the real facts into a harmless joke theory, and the Debunker uses the original
facts to bring it back down to earth. Agentarium records all three chapters,
their handoffs, the tool result, and the sources.

```bash
python -m examples.random_agent_chaos "why cats knock things off tables"
```

This makes real OpenAI and Tavily calls, so it uses API credits.

The browser should make the failure obvious: red Core for the error, amber
Core while retrying, then a recovered status after the task completes. The
completed flow table records the safe error messages and retry attempts.
