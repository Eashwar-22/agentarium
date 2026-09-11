(function exposeRunStory(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.AgentariumRunStory = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function createRunStory() {
  function stamp(event) {
    const value = Date.parse(event?.timestamp);
    return Number.isNaN(value) ? 0 : value;
  }

  function cleanUrl(value) {
    return String(value || "").trim().replace(/[.,;:!?)\]}>]+$/, "");
  }

  function urlsIn(value) {
    if (!value) return [];
    return String(value).match(/https?:\/\/[^\s<>"']+/g)?.map(cleanUrl) || [];
  }

  function sourceTitle(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch (_error) {
      return url;
    }
  }

  function buildRunStory(events) {
    const ordered = [...(events || [])].sort((left, right) => {
      const sequenceDifference = Number(left.sequence || 0) - Number(right.sequence || 0);
      return sequenceDifference || stamp(left) - stamp(right);
    });
    const runStart = ordered.find((event) => event.type === "run_started");
    const runEnd = [...ordered].reverse().find((event) => event.type === "run_completed");
    const agentNames = new Map();
    const agents = new Map();
    const sources = new Map();
    const openModels = new Map();
    const openTools = new Map();
    const openToolsByAgent = new Map();

    function ensureAgent(agentId) {
      if (!agentId) return null;
      if (!agents.has(agentId)) {
        agents.set(agentId, {
          id: agentId,
          name: agentNames.get(agentId) || agentId,
          firstTime: null,
          lastTime: null,
          intent: null,
          steps: [],
          modelCalls: 0,
          toolCalls: 0,
          errors: 0,
          sourceUrls: new Set(),
        });
      }
      const agent = agents.get(agentId);
      agent.name = agentNames.get(agentId) || agent.name;
      return agent;
    }

    function addSource(source, agent, stepSources) {
      const url = cleanUrl(source?.url || source);
      if (!url.startsWith("http://") && !url.startsWith("https://")) return;
      const existing = sources.get(url);
      const record = {
        url,
        title: source?.title || existing?.title || sourceTitle(url),
        snippet: source?.snippet || existing?.snippet || null,
        agents: existing?.agents || new Set(),
      };
      if (agent) {
        record.agents.add(agent.name);
        agent.sourceUrls.add(url);
      }
      sources.set(url, record);
      if (stepSources && !stepSources.includes(url)) stepSources.push(url);
    }

    function collectSources(event, agent) {
      const stepSources = [];
      (event.tool?.sources || []).forEach((source) => addSource(source, agent, stepSources));
      if (event.artifact?.uri) addSource(event.artifact.uri, agent, stepSources);
      const sourceText = [
        event.tool?.input_summary,
        event.tool?.output_summary,
        event.artifact?.preview,
        event.summary,
        JSON.stringify(event.metadata || {}),
      ].filter(Boolean).join(" ");
      urlsIn(sourceText).forEach((url) => addSource(url, agent, stepSources));
      return stepSources;
    }

    function addStep(agent, event, label, detail, meta = [], tone = "normal", stepSources = []) {
      if (!agent) return null;
      const time = stamp(event);
      agent.firstTime = agent.firstTime === null ? time : Math.min(agent.firstTime, time);
      agent.lastTime = agent.lastTime === null ? time : Math.max(agent.lastTime, time);
      const step = {
        sequence: event.sequence,
        type: event.type,
        time,
        label,
        detail,
        meta,
        tone,
        sources: stepSources,
      };
      agent.steps.push(step);
      return step;
    }

    ordered.forEach((event) => {
      if (event.type === "agent_spawned" && event.agent_id) {
        agentNames.set(event.agent_id, event.metadata?.name || event.metadata?.role || event.agent_id);
      }
      const agent = ensureAgent(event.agent_id);
      const eventSources = collectSources(event, agent);

      if (event.type === "agent_spawned") {
        addStep(agent, event, "Joined the run", `${agent.name} became available.`);
      } else if (event.type === "task_started") {
        const activity = event.metadata?.activity || event.summary;
        if (!agent.intent) agent.intent = activity;
        addStep(agent, event, "Task started", activity, [], "active");
      } else if (event.type === "model_started") {
        const queue = openModels.get(event.agent_id) || [];
        queue.push({
          start: stamp(event),
          activity: event.metadata?.activity || event.summary,
          model: event.metadata?.model || "Language model",
          inputItems: Number(event.metadata?.input_items || 0),
        });
        openModels.set(event.agent_id, queue);
      } else if (event.type === "model_completed") {
        const queue = openModels.get(event.agent_id) || [];
        const started = queue.shift();
        agent.modelCalls += 1;
        addStep(
          agent,
          event,
          "Model work",
          started?.activity || event.metadata?.activity || "Prepared the next response.",
          [
            ["Model", started?.model || "Language model"],
            ["Duration", started ? Math.max(0, stamp(event) - started.start) : null],
            ["Tokens", Number(event.metadata?.total_tokens || 0)],
          ],
        );
      } else if (event.type === "tool_started") {
        const key = `${event.agent_id}::${event.tool?.call_id || event.event_id}`;
        openTools.set(key, {
          start: stamp(event),
          input: event.tool?.input_summary || "No input summary recorded.",
          name: event.tool?.name || "Tool",
          failed: false,
        });
        const open = openToolsByAgent.get(event.agent_id) || [];
        open.push(key);
        openToolsByAgent.set(event.agent_id, open);
      } else if (event.type === "tool_completed") {
        const key = `${event.agent_id}::${event.tool?.call_id || event.event_id}`;
        const started = openTools.get(key);
        agent.toolCalls += 1;
        addStep(
          agent,
          event,
          started?.failed ? "Tool returned after an error" : "Tool call",
          event.tool?.output_summary || "Tool completed without an output summary.",
          [
            ["Tool", event.tool?.name || started?.name || "Tool"],
            ["Input", started?.input || "No input summary recorded."],
            ["Duration", started ? Math.max(0, stamp(event) - started.start) : null],
          ],
          started?.failed ? "warning" : "normal",
          eventSources,
        );
        openTools.delete(key);
        const open = openToolsByAgent.get(event.agent_id) || [];
        openToolsByAgent.set(event.agent_id, open.filter((item) => item !== key));
      } else if (event.type === "artifact_created") {
        addStep(
          agent,
          event,
          "Output saved",
          event.artifact?.preview || event.artifact?.title || event.summary,
          [["Type", event.artifact?.kind || "artifact"]],
          "success",
          eventSources,
        );
      } else if (event.type === "message_sent") {
        const target = agentNames.get(event.target_agent_id) || event.target_agent_id || "another agent";
        addStep(
          agent,
          event,
          `Message to ${target}`,
          event.metadata?.message || event.metadata?.note || event.summary,
        );
      } else if (event.type === "handoff_started") {
        const target = agentNames.get(event.target_agent_id) || event.target_agent_id || "another agent";
        addStep(agent, event, `Handoff to ${target}`, event.summary, [], "active", eventSources);
      } else if (event.type === "waiting") {
        addStep(agent, event, "Waiting", event.summary, [], "muted");
      } else if (event.type === "error") {
        agent.errors += 1;
        const open = openToolsByAgent.get(event.agent_id) || [];
        const activeTool = openTools.get(open.at(-1));
        if (activeTool) activeTool.failed = true;
        addStep(
          agent,
          event,
          "Error",
          event.error?.message || event.summary,
          [["Code", event.error?.code || "workflow_error"]],
          "error",
        );
      } else if (event.type === "retrying") {
        addStep(
          agent,
          event,
          "Retry",
          event.summary,
          [["Attempt", event.metadata?.attempt || null]],
          "warning",
        );
      } else if (event.type === "task_completed") {
        addStep(agent, event, "Task completed", event.summary, [], "success");
      } else if (event.type === "agent_completed") {
        addStep(agent, event, "Finished work", event.summary, [], "success");
      }
    });

    const storyAgents = [...agents.values()].map((agent) => ({
      ...agent,
      sourceUrls: [...agent.sourceUrls],
      durationMs: agent.firstTime === null ? 0 : Math.max(0, agent.lastTime - agent.firstTime),
    }));
    const storySources = [...sources.values()].map((source) => ({
      ...source,
      agents: [...source.agents],
    }));
    const timeline = storyAgents
      .flatMap((agent) => agent.steps.map((step) => ({
        ...step,
        agentId: agent.id,
        agentName: agent.name,
      })));
    if (runStart) {
      timeline.push({
        sequence: runStart.sequence,
        type: "run_started",
        time: stamp(runStart),
        label: "Run started",
        detail: runStart.metadata?.question || runStart.summary,
        meta: [],
        tone: "active",
        sources: [],
        agentId: null,
        agentName: "Workflow",
      });
    }
    if (runEnd) {
      timeline.push({
        sequence: runEnd.sequence,
        type: "run_completed",
        time: stamp(runEnd),
        label: runEnd.metadata?.status === "failed" ? "Run failed" : "Run completed",
        detail: runEnd.summary,
        meta: [],
        tone: runEnd.metadata?.status === "failed" ? "error" : "success",
        sources: [],
        agentId: null,
        agentName: "Workflow",
      });
    }
    timeline.sort((left, right) => Number(left.sequence || 0) - Number(right.sequence || 0));

    return {
      status: runEnd?.metadata?.status === "failed" ? "failed" : runEnd ? "succeeded" : ordered.length ? "running" : "waiting",
      question: runStart?.metadata?.question || "Agent workflow",
      startTime: stamp(runStart),
      endTime: stamp(runEnd || ordered.at(-1)),
      agents: storyAgents,
      sources: storySources,
      timeline,
      handoffs: ordered
        .filter((event) => event.type === "handoff_started")
        .map((event) => ({
          from: agentNames.get(event.agent_id) || event.agent_id,
          to: agentNames.get(event.target_agent_id) || event.target_agent_id,
        })),
    };
  }

  return { buildRunStory, urlsIn };
}));
