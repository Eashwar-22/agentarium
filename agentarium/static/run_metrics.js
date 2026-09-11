(function exposeRunMetrics(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.AgentariumRunMetrics = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function createRunMetrics() {
  function stamp(event) {
    const value = Date.parse(event?.timestamp);
    return Number.isNaN(value) ? 0 : value;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function taskKey(event) {
    return `${event.agent_id || "workflow"}::${event.task_id || event.event_id}`;
  }

  function toolKey(event) {
    return `${event.agent_id || "workflow"}::${event.tool?.call_id || event.event_id}`;
  }

  function normalizedToolInput(event) {
    return String(event.tool?.input_summary || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function calculateRunMetrics(events) {
    const ordered = [...(events || [])].sort((left, right) => {
      const sequenceDifference = Number(left.sequence || 0) - Number(right.sequence || 0);
      return sequenceDifference || stamp(left) - stamp(right);
    });
    const runStarted = ordered.find((event) => event.type === "run_started");
    const runCompleted = [...ordered].reverse().find((event) => event.type === "run_completed");
    const finalEvent = runCompleted || ordered.at(-1);
    const statusValue = runCompleted?.metadata?.status;
    const status = !runCompleted
      ? (ordered.length ? "running" : "waiting")
      : (statusValue === "failed" ? "failed" : "succeeded");

    const agentNames = new Map();
    const tasks = new Map();
    const tools = new Map();
    const openToolsByAgent = new Map();
    const agentDurations = new Map();
    const repeatedInputs = new Map();
    let inputTokens = 0;
    let outputTokens = 0;
    let totalTokens = 0;
    let reportedCost = 0;
    let hasReportedCost = false;
    let runReportedCost = null;
    let errors = 0;
    let retries = 0;

    ordered.forEach((event) => {
      if (event.type === "agent_spawned" && event.agent_id) {
        agentNames.set(
          event.agent_id,
          event.metadata?.name || event.metadata?.role || event.agent_id,
        );
      }

      if (event.type === "task_started") {
        tasks.set(taskKey(event), {
          agentId: event.agent_id,
          start: stamp(event),
          end: null,
        });
      }
      if (event.type === "task_completed") {
        const task = tasks.get(taskKey(event));
        if (task) task.end = stamp(event);
      }

      if (event.type === "tool_started") {
        const key = toolKey(event);
        tools.set(key, {
          agentId: event.agent_id,
          completed: false,
          failed: false,
        });
        const open = openToolsByAgent.get(event.agent_id) || [];
        open.push(key);
        openToolsByAgent.set(event.agent_id, open);

        const input = normalizedToolInput(event);
        if (input) {
          const signature = `${event.agent_id || "workflow"}::${event.tool?.name || "tool"}::${input}`;
          const repeat = repeatedInputs.get(signature) || {
            agentId: event.agent_id,
            toolName: event.tool?.name || "tool",
            input: event.tool?.input_summary || "",
            count: 0,
          };
          repeat.count += 1;
          repeatedInputs.set(signature, repeat);
        }
      }
      if (event.type === "tool_completed") {
        const key = toolKey(event);
        const tool = tools.get(key);
        if (tool) tool.completed = true;
        const open = openToolsByAgent.get(event.agent_id) || [];
        openToolsByAgent.set(event.agent_id, open.filter((item) => item !== key));
      }
      if (event.type === "error") {
        errors += 1;
        const open = openToolsByAgent.get(event.agent_id) || [];
        const activeTool = tools.get(open.at(-1));
        if (activeTool) activeTool.failed = true;
      }
      if (event.type === "retrying") retries += 1;

      if (event.type === "model_completed") {
        const eventInputTokens = Number(event.metadata?.input_tokens || 0);
        const eventOutputTokens = Number(event.metadata?.output_tokens || 0);
        inputTokens += eventInputTokens;
        outputTokens += eventOutputTokens;
        totalTokens += Number(event.metadata?.total_tokens || eventInputTokens + eventOutputTokens);
      }

      const cost = event.metadata?.cost_usd ?? event.metadata?.estimated_cost_usd;
      if (cost !== undefined && cost !== null && Number.isFinite(Number(cost))) {
        if (event.type === "run_completed") {
          runReportedCost = Number(cost);
        } else {
          reportedCost += Number(cost);
          hasReportedCost = true;
        }
      }
    });

    const metricEnd = stamp(finalEvent) || Date.now();
    tasks.forEach((task) => {
      const duration = Math.max(0, (task.end || metricEnd) - task.start);
      agentDurations.set(task.agentId, (agentDurations.get(task.agentId) || 0) + duration);
    });
    const bottleneckEntry = [...agentDurations.entries()]
      .sort((left, right) => right[1] - left[1])[0];
    const bottleneck = bottleneckEntry
      ? {
          agentId: bottleneckEntry[0],
          name: agentNames.get(bottleneckEntry[0]) || bottleneckEntry[0] || "Workflow",
          durationMs: bottleneckEntry[1],
        }
      : null;

    const taskValues = [...tasks.values()];
    const tasksCompleted = taskValues.filter((task) => task.end !== null).length;
    const toolValues = [...tools.values()];
    const toolsSucceeded = toolValues.filter((tool) => tool.completed && !tool.failed).length;
    const toolsFailed = toolValues.length - toolsSucceeded;
    const loops = [...repeatedInputs.values()].filter((repeat) => repeat.count >= 3);
    const durationMs = runStarted && finalEvent
      ? Math.max(0, stamp(finalEvent) - stamp(runStarted))
      : 0;

    let score = null;
    if (status === "succeeded" || status === "failed") {
      const completionRatio = taskValues.length ? tasksCompleted / taskValues.length : 1;
      score = 100;
      if (status === "failed") score -= 50;
      score -= Math.round((1 - completionRatio) * 25);
      score -= Math.min(30, toolsFailed * 10);
      score -= Math.min(20, errors * 5);
      score -= Math.min(10, retries * 2);
      score -= Math.min(20, loops.length * 10);
      score = clamp(score, 0, 100);
    }

    return {
      status,
      score,
      durationMs,
      tasksStarted: taskValues.length,
      tasksCompleted,
      toolCalls: toolValues.length,
      toolsSucceeded,
      toolsFailed,
      toolSuccessRate: toolValues.length
        ? Math.round((toolsSucceeded / toolValues.length) * 100)
        : null,
      inputTokens,
      outputTokens,
      totalTokens,
      costUsd: runReportedCost ?? (hasReportedCost ? reportedCost : null),
      errors,
      retries,
      bottleneck,
      loops,
    };
  }

  return { calculateRunMetrics };
}));
