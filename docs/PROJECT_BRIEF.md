# Project brief

## Problem

Agent workflows are hard to follow while they run. A spinner does not show
which agent is active, which tool is slow, why a retry happened, or where an
answer's sources came from. Raw traces contain the detail, but they are built
mainly for developers and take time to inspect.

## Product

Agentarium turns observable workflow events into a small live dashboard. Each
avatar represents a real agent. Its state changes when the workflow starts a
task, calls a model or tool, waits, retries, fails, or completes.

The UI also provides a normal developer trace, run metrics, source links, and a
start-to-finish run story. These views are generated from the saved event file
with local code. They do not make another model call.

## Event-to-UI mapping

| UI signal | Runtime meaning |
| --- | --- |
| Mind | Model activity and token usage |
| Hands | Tool calls and results |
| Core | Errors, retries, and recovery |
| Backpack | Sources and artifacts |
| Progress | Completed tasks |
| Waiting state | Dependency or handoff delay |

## First useful scope

- OpenAI Agents SDK adapter
- Live JSONL event stream over server-sent events
- Dynamic agents and tools; no frontend agent list
- Tool, source, artifact, error, retry, and handoff events
- Complete post-run timeline and scorecard
- Local dashboard with no extra model call

## Non-goals for the prototype

- Showing private chain-of-thought
- Replacing a full tracing backend
- Supporting every agent framework
- Remote hosting, accounts, or team access
- Letting the UI silently change a running workflow

## Example workflow

```text
Researcher -> Fact checker -> Writer
```

The Researcher searches the web and records sources. The Fact checker accepts
or rejects the evidence. The Writer receives the approved material. Agentarium
shows each step and keeps the complete run in `.agentarium/events.jsonl`.
