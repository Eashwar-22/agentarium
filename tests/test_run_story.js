const test = require("node:test");
const assert = require("node:assert/strict");

const { buildRunStory, urlsIn } = require("../agentarium/static/run_story.js");

function event(sequence, type, seconds, details = {}) {
  return {
    run_id: "run-story",
    event_id: `event-${sequence}`,
    sequence,
    type,
    timestamp: new Date(Date.UTC(2026, 0, 1, 0, 0, seconds)).toISOString(),
    metadata: {},
    ...details,
  };
}

test("builds an agent story from model, tool, source, and artifact events", () => {
  const events = [
    event(1, "run_started", 0, { metadata: { question: "What happened?" } }),
    event(2, "agent_spawned", 1, { agent_id: "scout", metadata: { name: "Scout" } }),
    event(3, "task_started", 2, { agent_id: "scout", task_id: "research", metadata: { activity: "Find reliable evidence." } }),
    event(4, "model_started", 3, { agent_id: "scout", task_id: "research", metadata: { activity: "Choose a search query.", model: "test-model" } }),
    event(5, "model_completed", 5, { agent_id: "scout", task_id: "research", metadata: { total_tokens: 42 } }),
    event(6, "tool_started", 6, { agent_id: "scout", task_id: "research", tool: { name: "search", call_id: "call-1", input_summary: "agent observability" } }),
    event(7, "tool_completed", 8, {
      agent_id: "scout",
      task_id: "research",
      tool: {
        name: "search",
        call_id: "call-1",
        output_summary: "Found one useful report.",
        sources: [{ title: "Useful report", url: "https://example.com/report", snippet: "Evidence." }],
      },
    }),
    event(8, "artifact_created", 9, { agent_id: "scout", task_id: "research", artifact: { kind: "answer", title: "Final answer", preview: "Short answer." } }),
    event(9, "task_completed", 10, { agent_id: "scout", task_id: "research", summary: "Research finished." }),
    event(10, "agent_completed", 11, { agent_id: "scout" }),
    event(11, "run_completed", 12, { metadata: { status: "succeeded" } }),
  ];

  const story = buildRunStory(events);
  assert.equal(story.status, "succeeded");
  assert.equal(story.question, "What happened?");
  assert.equal(story.agents[0].name, "Scout");
  assert.equal(story.agents[0].intent, "Find reliable evidence.");
  assert.equal(story.agents[0].modelCalls, 1);
  assert.equal(story.agents[0].toolCalls, 1);
  assert.equal(story.sources[0].title, "Useful report");
  assert.equal(story.sources[0].url, "https://example.com/report");
  assert.ok(story.agents[0].steps.some((step) => step.label === "Model work"));
  assert.ok(story.agents[0].steps.some((step) => step.detail === "Short answer."));
  assert.equal(story.timeline[0].label, "Run started");
  assert.equal(story.timeline.at(-1).label, "Run completed");
});

test("extracts source URLs from older event text", () => {
  const events = [
    event(1, "run_started", 0),
    event(2, "agent_spawned", 1, { agent_id: "agent-a", metadata: { name: "Agent A" } }),
    event(3, "artifact_created", 2, {
      agent_id: "agent-a",
      task_id: "task-a",
      artifact: { kind: "answer", title: "Answer", preview: "See https://example.org/source)." },
    }),
  ];

  const story = buildRunStory(events);
  assert.equal(story.sources[0].url, "https://example.org/source");
  assert.deepEqual(urlsIn("A https://example.org/a, and https://example.org/b."), [
    "https://example.org/a",
    "https://example.org/b",
  ]);
});
