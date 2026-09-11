# Agentarium event schema

Stage 2 defines the framework-independent boundary between an agent runtime and
the Agentarium interface. The adapter reports observable facts. The frontend
decides how those facts appear on an avatar.

Current schema version: `0.2`. Readers also accept `0.1` event files.

## Event envelope

Every event contains:

| Field | Meaning |
| --- | --- |
| `schema_version` | Version of this wire contract. |
| `run_id` | Groups all events from one workflow run. |
| `event_id` | Unique identity for deduplication and SSE reconnection. |
| `sequence` | Contiguous ordering within a run, beginning at `1`. |
| `timestamp` | Timezone-aware ISO 8601 timestamp. |
| `type` | One of the normalized event types below. |
| `summary` | Short, user-facing description without private reasoning. |

Optional structured fields are `agent_id`, `task_id`, `tool`,
`target_agent_id`, `artifact`, `error`, and `metadata`.

`metadata` is the escape hatch for small framework-specific or event-specific
facts. Information that becomes important across adapters should be promoted to
a typed field in a later schema version.

In version `0.2`, a completed tool may include `tool.sources`, a list of
observed `{title, url, snippet}` records. An artifact may include a short
`artifact.preview`. These fields let clients build readable run stories without
another model call. They contain observable output only, never private
chain-of-thought.

## Event types

| Type | Required structured data | Meaning |
| --- | --- | --- |
| `run_started` | — | A workflow run opened. |
| `agent_spawned` | `agent_id` | An agent became part of the run. |
| `task_started` | `agent_id`, `task_id` | An agent began an assigned unit of work. |
| `model_started` | `agent_id`, `task_id` | An agent sent observable input to an LLM. |
| `model_completed` | `agent_id`, `task_id` | An LLM call returned observable output and usage counts. |
| `tool_started` | `agent_id`, `task_id`, `tool` | A tool call began. |
| `tool_completed` | `agent_id`, `task_id`, `tool` | A tool call ended. |
| `artifact_created` | `agent_id`, `task_id`, `artifact` | An observable output was created. |
| `message_sent` | `agent_id`, `target_agent_id` | One agent sent a user-safe message. |
| `handoff_started` | `agent_id`, `target_agent_id` | Responsibility or evidence moved between agents. |
| `waiting` | `agent_id`, `task_id` | An agent paused for a dependency. |
| `retrying` | `agent_id`, `task_id` | An agent began another observable attempt. |
| `error` | `error` | A user-safe failure was observed; `agent_id` is optional. |
| `task_completed` | `agent_id`, `task_id` | An assigned unit of work ended. |
| `agent_completed` | `agent_id` | An agent finished its role in the run. |
| `run_completed` | — | The workflow run closed. |

## Complete-run invariants

A replayable complete run has one `run_id`, unique event IDs, contiguous
sequence numbers, non-decreasing timestamps, exactly one opening
`run_started`, and exactly one closing `run_completed`. Agents must spawn before
emitting work events, targets must already exist, and tool calls must start
before they complete.

## Privacy and presentation boundary

Events may expose actions, tools, artifacts, errors, handoffs, and short status
summaries. They must not contain private chain-of-thought. Tool inputs and
outputs use short summaries by default rather than raw prompts or responses.

The contract contains no body parts, colors, coordinates, animations, moods, or
other interface instructions. Those are derived by the consuming frontend. For
example, the current interface may map `tool_started` to illuminated hands, but
another client may render the same event as a timeline row.

## Versioning

Version `0.1` was intentionally narrow. Version `0.2` adds optional source and
artifact-preview fields while keeping old event files readable. A breaking field or semantic change
requires a new schema version. New information should remain in `metadata` only
while it is experimental; stable cross-adapter concepts should become typed
fields through an explicit schema revision.
