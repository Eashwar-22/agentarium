const test = require("node:test");
const assert = require("node:assert/strict");

const { calculateRunMetrics } = require("../agentarium/static/run_metrics.js");

function event(sequence, type, seconds, details = {}) {
  return {
    run_id: "run-test",
    event_id: `event-${sequence}`,
    sequence,
    type,
    timestamp: new Date(Date.UTC(2026, 0, 1, 0, 0, seconds)).toISOString(),
    metadata: {},
    ...details,
  };
}

test("calculates a successful run and its bottleneck", () => {
  const events = [
    event(1, "run_started", 0),
    event(2, "agent_spawned", 1, { agent_id: "fast", metadata: { name: "Fast Agent" } }),
    event(3, "agent_spawned", 2, { agent_id: "slow", metadata: { name: "Slow Agent" } }),
    event(4, "task_started", 3, { agent_id: "fast", task_id: "fast-task" }),
    event(5, "task_completed", 5, { agent_id: "fast", task_id: "fast-task" }),
    event(6, "task_started", 6, { agent_id: "slow", task_id: "slow-task" }),
    event(7, "model_completed", 8, {
      agent_id: "slow",
      task_id: "slow-task",
      metadata: { input_tokens: 70, output_tokens: 30, total_tokens: 100 },
    }),
    event(8, "task_completed", 16, { agent_id: "slow", task_id: "slow-task" }),
    event(9, "run_completed", 17, { metadata: { status: "succeeded" } }),
  ];

  const metrics = calculateRunMetrics(events);
  assert.equal(metrics.status, "succeeded");
  assert.equal(metrics.score, 100);
  assert.equal(metrics.durationMs, 17000);
  assert.equal(metrics.tasksCompleted, 2);
  assert.equal(metrics.totalTokens, 100);
  assert.equal(metrics.bottleneck.name, "Slow Agent");
  assert.equal(metrics.bottleneck.durationMs, 10000);
});

test("marks errors during tool calls as failures", () => {
  const events = [
    event(1, "run_started", 0),
    event(2, "agent_spawned", 1, { agent_id: "scout", metadata: { name: "Scout" } }),
    event(3, "task_started", 2, { agent_id: "scout", task_id: "lookup" }),
    event(4, "tool_started", 3, { agent_id: "scout", tool: { name: "lookup", call_id: "one", input_summary: "first" } }),
    event(5, "error", 4, { agent_id: "scout", error: { message: "temporary", retryable: true } }),
    event(6, "tool_completed", 5, { agent_id: "scout", tool: { name: "lookup", call_id: "one" } }),
    event(7, "retrying", 6, { agent_id: "scout" }),
    event(8, "tool_started", 7, { agent_id: "scout", tool: { name: "lookup", call_id: "two", input_summary: "second" } }),
    event(9, "tool_completed", 8, { agent_id: "scout", tool: { name: "lookup", call_id: "two" } }),
    event(10, "task_completed", 9, { agent_id: "scout", task_id: "lookup" }),
    event(11, "run_completed", 10, { metadata: { status: "succeeded" } }),
  ];

  const metrics = calculateRunMetrics(events);
  assert.equal(metrics.toolCalls, 2);
  assert.equal(metrics.toolsSucceeded, 1);
  assert.equal(metrics.toolsFailed, 1);
  assert.equal(metrics.toolSuccessRate, 50);
  assert.equal(metrics.errors, 1);
  assert.equal(metrics.retries, 1);
  assert.equal(metrics.score, 83);
});

test("prefers an aggregate run cost over per-call costs", () => {
  const events = [
    event(1, "run_started", 0),
    event(2, "model_completed", 1, { metadata: { total_tokens: 20, cost_usd: 0.01 } }),
    event(3, "model_completed", 2, { metadata: { total_tokens: 30, cost_usd: 0.02 } }),
    event(4, "run_completed", 3, { metadata: { status: "succeeded", cost_usd: 0.025 } }),
  ];

  const metrics = calculateRunMetrics(events);
  assert.equal(metrics.costUsd, 0.025);
  assert.equal(metrics.totalTokens, 50);
});

test("warns only when the same tool input repeats three times", () => {
  const events = [event(1, "run_started", 0)];
  for (let index = 0; index < 3; index += 1) {
    events.push(event(2 + index * 2, "tool_started", 1 + index * 2, {
      agent_id: "agent",
      tool: { name: "search", call_id: `call-${index}`, input_summary: "same query" },
    }));
    events.push(event(3 + index * 2, "tool_completed", 2 + index * 2, {
      agent_id: "agent",
      tool: { name: "search", call_id: `call-${index}` },
    }));
  }
  events.push(event(8, "run_completed", 8, { metadata: { status: "succeeded" } }));

  const metrics = calculateRunMetrics(events);
  assert.equal(metrics.loops.length, 1);
  assert.equal(metrics.loops[0].count, 3);
  assert.equal(metrics.score, 90);
});
