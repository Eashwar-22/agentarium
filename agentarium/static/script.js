const SVG_NS = "http://www.w3.org/2000/svg";
// Every normal agent uses the same calm cyan. Color changes are reserved for
// meaningful diagnostics, not agent identity.
const colors = ["#52dfd5"];
const eventTypes = [
  "run_started", "agent_spawned", "task_started", "model_started",
  "model_completed", "tool_started",
  "tool_completed", "artifact_created", "message_sent", "handoff_started",
  "waiting", "retrying", "error", "task_completed", "agent_completed",
  "run_completed",
];
const bodyPartByEvent = {
  agent_spawned: "core",
  task_started: "head",
  model_started: "head",
  model_completed: "head",
  tool_started: "hands",
  tool_completed: "hands",
  artifact_created: "pack",
  message_sent: "hands",
  handoff_started: "hands",
  waiting: "core",
  retrying: "core",
  error: "core",
  task_completed: "legs",
  agent_completed: "legs",
};
const partLabels = { head: "Mind", hands: "Hands", core: "Core", pack: "Artifact", legs: "Progress" };
const partSymbols = { head: "◉", hands: "↔", core: "◈", pack: "◇", legs: "▲" };

const agentField = document.querySelector(".agent-field");
const stageScroll = document.querySelector(".stage-scroll");
const runButton = document.querySelector("#run-button");
const pauseButton = document.querySelector("#pause-button");
const speedSelect = document.querySelector("#speed-select");
const runDot = document.querySelector("#run-dot");
const runLabel = document.querySelector("#run-label");
const eventList = document.querySelector("#event-list");
const eventCount = document.querySelector("#event-count");
const signalSymbol = document.querySelector("#signal-symbol");
const signalSource = document.querySelector("#signal-source");
const signalMessage = document.querySelector("#signal-message");
const signalType = document.querySelector("#signal-type");
const missionTitle = document.querySelector("#mission-title");
const missionEyebrow = document.querySelector(".mission-header .eyebrow");
const inspectorTitle = document.querySelector("#inspector-title");
const inspectorHint = document.querySelector("#inspector-hint");
const traceList = document.querySelector("#trace-list");
const traceSummary = document.querySelector("#trace-summary");
const flowMap = document.querySelector("#flow-map");
const flowSummary = document.querySelector("#flow-summary");
const scorecardState = document.querySelector("#scorecard-state");
const executionScore = document.querySelector("#execution-score");
const executionScoreValue = document.querySelector("#execution-score-value");
const scoreVerdict = document.querySelector("#score-verdict");
const scoreNote = document.querySelector("#score-note");
const metricStatus = document.querySelector("#metric-status");
const metricStatusNote = document.querySelector("#metric-status-note");
const metricDuration = document.querySelector("#metric-duration");
const metricTools = document.querySelector("#metric-tools");
const metricToolsNote = document.querySelector("#metric-tools-note");
const metricTokens = document.querySelector("#metric-tokens");
const metricCost = document.querySelector("#metric-cost");
const metricTasks = document.querySelector("#metric-tasks");
const metricRecovery = document.querySelector("#metric-recovery");
const metricBottleneck = document.querySelector("#metric-bottleneck");
const metricLoops = document.querySelector("#metric-loops");
const storyState = document.querySelector("#story-state");
const storyOverview = document.querySelector("#story-overview");
const storyAgents = document.querySelector("#story-agents");
const storyStepCount = document.querySelector("#story-step-count");
const storyTimeline = document.querySelector("#story-timeline");
const storySourceCount = document.querySelector("#story-source-count");
const storySourceList = document.querySelector("#story-source-list");
const inspectorParts = Object.fromEntries(
  [...document.querySelectorAll("[data-inspector-part]")].map((item) => [item.dataset.inspectorPart, item]),
);
const inspectorStatusParts = Object.fromEntries(
  [...document.querySelectorAll("[data-status-part]")].map((item) => [item.dataset.statusPart, item]),
);

const agents = new Map();
const eventQueue = [];
const observedEvents = [];
let runStartedAt = 0;
let receivedEvents = 0;
let currentRunId = null;
let selectedAgentId = null;
let processingEvent = false;
let playbackPaused = false;
let playbackSpeed = 1;

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function drawFloor(width) {
  const floor = svgElement("g", { class: "floor-grid", "aria-hidden": "true" });
  const guides = [];
  for (let x = 150; x < width; x += 300) guides.push(`M${x} 411V251`);
  floor.innerHTML = `
    <path d="M44 371H${width - 44}M88 331H${width - 88}M132 291H${width - 132}" />
    <path d="${guides.join("")}" />
  `;
  agentField.prepend(floor);
}

function splitAgentName(name) {
  if (name.length <= 20) return [name];
  const words = name.split(/\s+/);
  let firstLine = "";
  let secondLine = "";
  words.forEach((word) => {
    if (!secondLine && `${firstLine} ${word}`.trim().length <= 20) {
      firstLine = `${firstLine} ${word}`.trim();
    } else {
      secondLine = `${secondLine} ${word}`.trim();
    }
  });
  if (!firstLine) {
    firstLine = name.slice(0, 19);
    secondLine = name.slice(19);
  }
  if (!secondLine) return [firstLine];
  return [firstLine, secondLine.length > 23 ? `${secondLine.slice(0, 22)}…` : secondLine];
}

function setAvatarName(avatar, name) {
  const label = avatar.querySelector(".agent-name");
  const lines = splitAgentName(name);
  label.textContent = "";
  label.setAttribute("y", lines.length === 1 ? "-26" : "-38");
  lines.forEach((line, index) => {
    const textLine = svgElement("tspan", { x: "0", dy: index === 0 ? "0" : "16" });
    textLine.textContent = line;
    label.append(textLine);
  });
}

function resetView(question = "Waiting for a research run…") {
  agents.clear();
  observedEvents.length = 0;
  agentField.innerHTML = "";
  agentField.setAttribute("viewBox", "0 0 1200 440");
  agentField.dataset.fieldWidth = "1200";
  agentField.style.minWidth = "960px";
  drawFloor(1200);
  receivedEvents = 0;
  runStartedAt = Date.now();
  missionTitle.textContent = question;
  eventCount.textContent = "0 events";
  eventList.innerHTML = '<li class="empty-event">Run a wrapped workflow to see real events.</li>';
  signalSymbol.textContent = "○";
  signalSource.textContent = "No active agent";
  signalMessage.textContent = "Start a workflow to see what the agents are doing.";
  signalType.textContent = "idle";
  runDot.className = "run-dot";
  runLabel.textContent = "Live listener ready";
  selectedAgentId = null;
  inspectorTitle.textContent = "Waiting for activity";
  inspectorHint.textContent = "Live view";
  Object.values(inspectorParts).forEach((item) => {
    item.classList.remove("active");
  });
  Object.values(inspectorStatusParts).forEach((item) => {
    item.classList.remove("active", "has-data");
  });
  inspectorParts.head.querySelector("strong").textContent = "Nothing observed yet";
  inspectorParts.hands.querySelector("strong").textContent = "Nothing observed yet";
  inspectorParts.core.querySelector("strong").textContent = "Healthy · no errors";
  inspectorParts.pack.querySelector("strong").textContent = "No artifacts yet";
  inspectorParts.legs.querySelector("strong").textContent = "Waiting to start";
  traceSummary.textContent = "Waiting for events";
  traceList.innerHTML = '<p class="empty-observability">Agent and tool spans will appear here during the run.</p>';
  flowSummary.textContent = "Available when the run finishes";
  flowMap.innerHTML = '<p class="empty-observability">The final agent and tool map will appear here.</p>';
  scorecardState.textContent = "Waiting for a run";
  executionScoreValue.textContent = "—";
  executionScore.style.setProperty("--score-angle", "0deg");
  executionScore.style.setProperty("--score-color", "#516a82");
  executionScore.setAttribute("aria-label", "Execution score not available");
  scoreVerdict.textContent = "No run yet";
  scoreNote.textContent = "Starts at 100. Failures, unfinished work, errors, retries, and repeated identical calls lower it.";
  metricStatus.textContent = "Waiting";
  metricStatusNote.textContent = "No workflow observed";
  metricDuration.textContent = "—";
  metricTools.textContent = "—";
  metricToolsNote.textContent = "No calls observed";
  metricTokens.textContent = "—";
  metricCost.textContent = "Cost not reported";
  metricTasks.textContent = "—";
  metricRecovery.textContent = "—";
  metricBottleneck.textContent = "Waiting for task timing";
  metricLoops.textContent = "No repeated identical calls";
  storyState.textContent = "Waiting for a run";
  storyOverview.innerHTML = '<p class="empty-observability">Run a workflow to build its story.</p>';
  storyAgents.innerHTML = "";
  storyStepCount.textContent = "0 steps";
  storyTimeline.innerHTML = "";
  storySourceCount.textContent = "0 sources";
  storySourceList.innerHTML = '<p class="empty-observability">No source links recorded yet.</p>';
  document.querySelectorAll(".metric-grid article").forEach((item) => {
    item.classList.remove("good", "bad", "attention");
  });
}

function registerAgent(event) {
  if (!event.agent_id || agents.has(event.agent_id)) return agents.get(event.agent_id);

  const index = agents.size;
  const x = 150 + index * 300;
  const width = Math.max(1200, (index + 1) * 300);
  const name = event.metadata?.name || event.metadata?.role || event.agent_id;
  const accent = colors[index % colors.length];
  const avatar = svgElement("g", {
    class: "avatar",
    "data-agent": event.agent_id,
    transform: `translate(${x} 42)`,
    style: `--agent-accent:${accent}`,
  });
  avatar.innerHTML = `
    <text class="agent-index" x="-110" y="-26">${String(index + 1).padStart(2, "0")}</text>
    <text class="agent-name" x="0" y="-26"></text>
    <g class="body-part legs-part" data-part="legs"><path d="M-34 265h27l-7 73h-31ZM7 265h27l11 73H14Z" /><rect x="-48" y="337" width="36" height="10" rx="5" /><rect x="12" y="337" width="36" height="10" rx="5" /></g>
    <g class="body-part core-part" data-part="core"><rect x="-44" y="126" width="88" height="145" rx="38" /></g>
    <g class="body-part pack-part" data-part="pack"><path d="M0 166 20 190 0 214-20 190Z" /><path class="artifact-mark" d="M-8 190h16" /></g>
    <g class="body-part hands-part" data-part="hands"><path d="m-37 153-18 10-38 68 18 11 39-57ZM37 153l18 10 38 68-18 11-39-57Z" /><circle cx="-83" cy="239" r="13" /><circle cx="83" cy="239" r="13" /></g>
    <g class="body-part head-part" data-part="head"><circle cx="0" cy="76" r="43" /><path class="face-mark" d="M-19 75h10m18 0h10M-15 93c9 7 21 7 30 0" /></g>
    <text class="avatar-status" x="0" y="379">Discovered</text>
  `;
  setAvatarName(avatar, name);
  agentField.append(avatar);
  agentField.setAttribute("viewBox", `0 0 ${width} 440`);
  agentField.dataset.fieldWidth = String(width);
  agentField.style.minWidth = `${Math.max(960, width * 0.8)}px`;

  const record = {
    id: event.agent_id,
    element: avatar,
    index,
    name,
    x,
    latestPart: "core",
    details: {
      head: "Nothing observed yet",
      hands: "Nothing observed yet",
      core: "Healthy · no errors",
      pack: "No artifacts yet",
      legs: "Waiting to start",
    },
    latestAction: `${name} is ready.`,
    latestType: "agent_spawned",
    diagnostic: null,
  };
  agents.set(event.agent_id, record);
  attachBodyTooltipHandlers(record);
  avatar.addEventListener("click", () => selectAgent(event.agent_id));
  return record;
}

function showConnection(event) {
  if (!event.agent_id || !event.target_agent_id) return;
  const source = agents.get(event.agent_id);
  const target = agents.get(event.target_agent_id);
  if (!source || !target) return;

  const movingRight = source.x < target.x;
  const startX = source.x + (movingRight ? 79 : -79);
  const endX = target.x + (movingRight ? -79 : 79);
  const middleX = (startX + endX) / 2;
  const connection = svgElement("g", { class: "connection active" });
  connection.innerHTML = `
    <path class="connection-path" d="M${startX} 280 C${middleX} 247 ${middleX} 247 ${endX} 280" />
    <circle class="hand-joint" cx="${middleX}" cy="258" r="9" />
    <circle class="artifact-token" cx="0" cy="0" r="8" />
  `;
  agentField.insertBefore(connection, agentField.querySelector(".avatar"));
  connection.querySelector(".artifact-token").animate(
    [
      { transform: `translate(${startX}px, 280px)` },
      { transform: `translate(${middleX}px, 258px)` },
      { transform: `translate(${endX}px, 280px)` },
    ],
    { duration: 1100, easing: "ease-in-out" },
  );
  setTimeout(() => connection.remove(), 1400);
}

function avatarStatus(event) {
  const states = {
    agent_spawned: "Discovered",
    model_started: "Thinking",
    waiting: "Waiting",
    retrying: "Retrying",
    error: "Error",
    task_completed: "Step done",
    agent_completed: "Done",
  };
  return states[event.type] || "Active";
}

function activityCueLabel(event) {
  if (event.type === "model_started") return "thinking…";
  if (event.type === "tool_started") {
    const toolName = event.tool?.name || "tool";
    return toolName.length > 30 ? `${toolName.slice(0, 29)}…` : toolName;
  }
  return null;
}

function clearActivityCues(avatar = agentField) {
  avatar.querySelectorAll(".activity-cue").forEach((item) => item.remove());
}

function showActivityCue(event, record) {
  const label = activityCueLabel(event);
  if (!label) return;
  clearActivityCues(record.element);

  const fieldWidth = Number(agentField.dataset.fieldWidth) || 1200;
  let direction = record.index % 2 === 0 ? 1 : -1;
  if (record.x > fieldWidth - 220) direction = -1;
  if (record.x < 220) direction = 1;

  const isTool = event.type === "tool_started";
  const x = isTool ? direction * 55 : 0;
  const y = isTool ? 135 : 12;
  const cueDuration = Math.max(650, 1250 / playbackSpeed);
  const cue = svgElement("g", {
    class: `activity-cue ${isTool ? "tool-cue" : "thinking-cue"}`,
    transform: `translate(${x} ${y})`,
    style: `--cue-duration:${cueDuration}ms`,
    "aria-label": label,
  });
  const text = svgElement("text", {
    x: "0",
    y: "0",
    "text-anchor": isTool ? (direction > 0 ? "start" : "end") : "middle",
  });
  text.textContent = label;
  cue.append(text);
  record.element.append(cue);
  window.setTimeout(() => cue.remove(), cueDuration + 50);
}

function centerActiveAgent(record) {
  window.requestAnimationFrame(() => {
    const fieldWidth = Number(agentField.dataset.fieldWidth) || 1200;
    const renderedWidth = agentField.getBoundingClientRect().width;
    const center = (record.x / fieldWidth) * renderedWidth;
    const left = Math.max(0, center - stageScroll.clientWidth / 2);
    stageScroll.scrollTo({ left, behavior: "smooth" });
  });
}

function detailForEvent(event) {
  if (event.type === "model_started") {
    const activity = event.metadata?.activity || "Preparing the next observable response";
    return `${activity} · ${event.metadata?.input_items || 0} input item(s)`;
  }
  if (event.type === "model_completed") {
    const activity = event.metadata?.activity || "Observable response completed";
    return `${activity} · ${event.metadata?.total_tokens || 0} tokens used`;
  }
  if (event.type === "tool_started") {
    return `${event.tool.name}: ${event.tool.input_summary || "Tool call started"}`;
  }
  if (event.type === "tool_completed") {
    return `${event.tool.name}: ${event.tool.output_summary || "Tool call completed"}`;
  }
  if (event.type === "artifact_created") {
    return `${event.artifact.title} · ${event.artifact.kind}`;
  }
  if (event.type === "error") {
    return event.error?.message || event.summary;
  }
  return event.summary;
}

function eventTime(event) {
  const value = Date.parse(event.timestamp);
  return Number.isNaN(value) ? Date.now() : value;
}

function formatDuration(start, end) {
  const milliseconds = Math.max(0, end - start);
  if (milliseconds < 10) return "<10ms";
  if (milliseconds < 1000) return `${Math.round(milliseconds)}ms`;
  return `${(milliseconds / 1000).toFixed(1)}s`;
}

function tooltipLines(value, maxLength = 29, maxLines = 3) {
  const text = String(value || "No details recorded yet.").replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) return [text];
  if (!text.includes(" ")) return [`${text.slice(0, maxLength - 1)}…`];

  const lines = [];
  let line = "";
  for (const word of text.split(" ")) {
    const candidate = line ? `${line} ${word}` : word;
    if (candidate.length <= maxLength) {
      line = candidate;
      continue;
    }
    if (line) lines.push(line);
    line = word;
    if (lines.length === maxLines - 1) break;
  }
  if (line && lines.length < maxLines) lines.push(line);
  const covered = lines.join(" ");
  if (covered.length < text.length && lines.length) {
    lines[lines.length - 1] = `${lines[lines.length - 1].slice(0, maxLength - 1)}…`;
  }
  return lines.slice(0, maxLines);
}

function bodyTooltipContent(record, part) {
  const agentEvents = observedEvents.filter((item) => item.agent_id === record.id);
  const toolEvents = agentEvents.filter((item) => item.type === "tool_started");
  const modelEvents = agentEvents.filter((item) => item.type === "model_started");
  const errorEvents = agentEvents.filter((item) => item.type === "error");
  const retryEvents = agentEvents.filter((item) => item.type === "retrying");
  const artifacts = agentEvents.filter((item) => item.type === "artifact_created");
  const taskStarts = agentEvents.filter((item) => item.type === "task_started");
  const completedTasks = agentEvents.filter((item) => item.type === "task_completed");
  const lastTool = toolEvents.at(-1)?.tool?.name;
  const lastArtifact = artifacts.at(-1)?.artifact?.title;
  const latestRetry = retryEvents.at(-1)?.metadata?.attempt;

  if (part === "head") {
    return {
      title: "Mind",
      lines: modelEvents.length
        ? [`${modelEvents.length} model ${modelEvents.length === 1 ? "call" : "calls"}`, record.details.head]
        : ["No model call recorded", record.details.head],
    };
  }
  if (part === "hands") {
    return {
      title: "Hands",
      lines: toolEvents.length
        ? [`${toolEvents.length} tool ${toolEvents.length === 1 ? "call" : "calls"}`, `Latest: ${lastTool}`]
        : ["No tool call recorded", record.details.hands],
    };
  }
  if (part === "core") {
    if (errorEvents.length) {
      return {
        title: "Core",
        lines: [
          `${errorEvents.length} ${errorEvents.length === 1 ? "error" : "errors"} observed`,
          latestRetry ? `Recovered on attempt ${latestRetry}` : "Recovery not complete",
          errorEvents.at(-1)?.error?.code || errorEvents.at(-1)?.error?.message || record.details.core,
        ],
      };
    }
    return {
      title: "Core",
      lines: [record.diagnostic?.detail || "Healthy · no errors", record.details.core],
    };
  }
  if (part === "pack") {
    return {
      title: "Artifact",
      lines: artifacts.length
        ? [`${artifacts.length} artifact${artifacts.length === 1 ? "" : "s"} created`, `Latest: ${lastArtifact}`]
        : ["No artifact recorded", record.details.pack],
    };
  }
  return {
    title: "Progress",
    lines: taskStarts.length
      ? [`${completedTasks.length}/${taskStarts.length} task${taskStarts.length === 1 ? "" : "s"} complete`, record.details.legs]
      : ["No task started", record.details.legs],
  };
}

function hideBodyTooltip(avatar) {
  avatar.querySelector(".body-tooltip")?.remove();
}

function showBodyTooltip(record, part) {
  const avatar = record.element;
  hideBodyTooltip(avatar);
  const { title, lines } = bodyTooltipContent(record, part);
  // Keep the edge avatars' cards on their right, open side. This is especially
  // important for a two-agent run: the second card must not cover agent one.
  const direction = record.index > 0 && record.index < agents.size - 1 && record.index % 2
    ? -1
    : 1;
  const anchors = {
    head: { x: 60, y: 42 },
    hands: { x: 104, y: 174 },
    core: { x: 60, y: 176 },
    pack: { x: 60, y: 205 },
    legs: { x: 60, y: 282 },
  };
  const anchor = anchors[part] || anchors.core;
  const visibleLines = lines.flatMap((line) => tooltipLines(line)).slice(0, 3);
  const width = 164;
  const padding = 10;
  const lineHeight = 14;
  const height = 31 + (visibleLines.length * lineHeight);
  const x = direction * anchor.x;
  const cardX = direction > 0 ? 0 : -width;
  const textX = direction > 0 ? padding : -(width - padding);
  const textAnchor = direction > 0 ? "start" : "end";
  const tooltip = svgElement("g", {
    class: "body-tooltip",
    transform: `translate(${x} ${anchor.y})`,
    "aria-label": `${title}: ${visibleLines.join(". ")}`,
  });
  tooltip.innerHTML = `<rect x="${cardX}" y="-17" width="${width}" height="${height}" rx="7" />
    <text class="body-tooltip-title" x="${textX}" y="0" text-anchor="${textAnchor}">${title}</text>`;
  visibleLines.forEach((line, index) => {
    const detail = svgElement("text", {
      class: "body-tooltip-line",
      x: textX,
      y: 16 + (index * lineHeight),
      "text-anchor": textAnchor,
    });
    detail.textContent = line;
    tooltip.append(detail);
  });
  avatar.append(tooltip);
}

function attachBodyTooltipHandlers(record) {
  record.element.querySelectorAll(".body-part").forEach((bodyPart) => {
    const part = bodyPart.dataset.part;
    bodyPart.setAttribute("aria-label", `${part} details`);
    bodyPart.addEventListener("pointerenter", () => showBodyTooltip(record, part));
    bodyPart.addEventListener("pointerleave", () => hideBodyTooltip(record.element));
  });
}

function agentDiagnostic(record, event) {
  const agentEvents = observedEvents.filter((item) => item.agent_id === event.agent_id);
  const toolEvents = agentEvents.filter((item) => item.type === "tool_started");
  const toolCounts = new Map();
  toolEvents.forEach((item) => {
    const name = item.tool?.name || "tool";
    toolCounts.set(name, (toolCounts.get(name) || 0) + 1);
  });
  const [mostUsedTool = "", mostUsedCount = 0] = [...toolCounts.entries()]
    .sort(([, left], [, right]) => right - left)[0] || [];
  const taskStart = agentEvents.find((item) => item.type === "task_started");
  const elapsed = taskStart ? eventTime(event) - eventTime(taskStart) : 0;
  const errorEvents = agentEvents.filter((item) => item.type === "error");
  const latestState = agentEvents
    .filter((item) => ["error", "retrying", "waiting"].includes(item.type))
    .at(-1);
  const completedAfterState = latestState && agentEvents.some(
    (item) => item.type === "task_completed" && eventTime(item) > eventTime(latestState),
  );
  const mode = completedAfterState ? "normal" : latestState?.type || "normal";
  const toolLoop = mostUsedCount >= 3;
  const bottleneck = elapsed >= 15000;
  const errorCount = errorEvents.length;
  const latestError = errorEvents.at(-1);
  let label = "";
  let detail = "";

  if (mode === "error") {
    label = "Error";
    detail = latestError?.error?.message || "An observable workflow error occurred.";
  } else if (mode === "retrying") {
    label = "Retrying";
    detail = `Retry attempt ${latestState?.metadata?.attempt || "in progress"}.`;
  } else if (mode === "waiting") {
    label = "Waiting";
    detail = latestState?.metadata?.waiting_for
      ? `Waiting for ${latestState.metadata.waiting_for}.`
      : "Waiting for another workflow step.";
  } else if (errorCount) {
    label = `Recovered · ${errorCount} ${errorCount === 1 ? "error" : "errors"}`;
    detail = `Recovered after ${errorCount} observable ${errorCount === 1 ? "error" : "errors"}.`;
  } else if (toolLoop && bottleneck) {
    label = `${mostUsedCount} calls · ${formatDuration(0, elapsed)}`;
    detail = `${mostUsedTool} ran ${mostUsedCount} times over ${formatDuration(0, elapsed)}.`;
  } else if (toolLoop) {
    label = `${mostUsedCount} tool calls`;
    detail = `${mostUsedTool} ran ${mostUsedCount} times.`;
  } else if (bottleneck) {
    label = `Slow · ${formatDuration(0, elapsed)}`;
    detail = `This task has been active for ${formatDuration(0, elapsed)}.`;
  }

  return { mode, toolLoop, bottleneck, errorCount, label, detail };
}

function addDiagnosticMarker(avatar, part, tone) {
  const positions = {
    head: { x: 54, y: 43 },
    hands: { x: 103, y: 151 },
    core: { x: 58, y: 142 },
  };
  const position = positions[part];
  if (!position) return;
  const marker = svgElement("g", {
    class: `diagnostic-marker ${tone}`,
    transform: `translate(${position.x} ${position.y})`,
    "aria-hidden": "true",
  });
  marker.innerHTML = '<circle r="10" /><text x="0" y="1">!</text>';
  avatar.append(marker);
}

function updateDiagnosticMarkers(avatar, diagnostic) {
  avatar.querySelectorAll(".diagnostic-marker").forEach((marker) => marker.remove());
  if (diagnostic.bottleneck) addDiagnosticMarker(avatar, "head", "slow");
  if (diagnostic.toolLoop) addDiagnosticMarker(avatar, "hands", "attention");
  if (diagnostic.mode === "error") addDiagnosticMarker(avatar, "core", "error");
  if (diagnostic.mode === "retrying" || (diagnostic.errorCount && diagnostic.mode === "normal")) {
    addDiagnosticMarker(avatar, "core", "attention");
  }
}

function applyDiagnosticState(record, event) {
  const diagnostic = agentDiagnostic(record, event);
  record.diagnostic = diagnostic;
  const avatar = record.element;
  avatar.classList.toggle("error", diagnostic.mode === "error");
  avatar.classList.toggle("retrying", diagnostic.mode === "retrying");
  avatar.classList.toggle("waiting", diagnostic.mode === "waiting");
  avatar.classList.toggle("recovered", diagnostic.errorCount > 0 && diagnostic.mode === "normal");
  avatar.classList.toggle("tool-loop", diagnostic.toolLoop);
  avatar.classList.toggle("bottleneck", diagnostic.bottleneck);
  avatar.querySelector(".avatar-status").textContent = diagnostic.label || avatarStatus(event);
  updateDiagnosticMarkers(avatar, diagnostic);
  if (diagnostic.detail) record.details.core = diagnostic.detail;
}

function traceModel(events) {
  const records = new Map();
  const openTasks = new Map();
  const openModels = new Map();
  const openTools = new Map();
  const lastTime = events.length ? eventTime(events[events.length - 1]) : Date.now();

  const ensureAgent = (event) => {
    if (!event.agent_id) return null;
    if (!records.has(event.agent_id)) {
      records.set(event.agent_id, {
        id: event.agent_id,
        name: event.metadata?.name || event.metadata?.role || agents.get(event.agent_id)?.name || event.agent_id,
        start: eventTime(event),
        end: null,
        state: "running",
        spans: [],
      });
    }
    const record = records.get(event.agent_id);
    if (event.metadata?.name) record.name = event.metadata.name;
    return record;
  };

  const startSpan = (record, kind, label, event, metadata = {}) => {
    const span = { kind, label, start: eventTime(event), end: null, state: "running", metadata };
    record.spans.push(span);
    return span;
  };

  events.forEach((event) => {
    const record = ensureAgent(event);
    if (!record) return;
    if (event.type === "agent_spawned") record.start = eventTime(event);
    if (event.type === "task_started") {
      const span = startSpan(record, "task", "Agent task", event, {
        Activity: event.metadata?.activity || event.summary,
      });
      openTasks.set(event.task_id || event.event_id, span);
    }
    if (event.type === "task_completed") {
      const span = openTasks.get(event.task_id);
      if (span) {
        span.end = eventTime(event);
        span.state = "complete";
        openTasks.delete(event.task_id);
      }
    }
    if (event.type === "model_started") {
      const span = startSpan(record, "model", event.metadata?.model || "Language model", event, {
        Activity: event.metadata?.activity || "Preparing an observable response",
        Input: `${event.metadata?.input_items || 0} item(s)`,
      });
      const queue = openModels.get(event.agent_id) || [];
      queue.push(span);
      openModels.set(event.agent_id, queue);
    }
    if (event.type === "model_completed") {
      const queue = openModels.get(event.agent_id) || [];
      const span = queue.shift();
      if (span) {
        span.end = eventTime(event);
        span.state = "complete";
        span.metadata.Output = `${event.metadata?.output_items || 0} item(s)`;
        span.metadata.Tokens = `${event.metadata?.input_tokens || 0} in · ${event.metadata?.output_tokens || 0} out · ${event.metadata?.total_tokens || 0} total`;
      }
    }
    if (event.type === "tool_started") {
      const span = startSpan(record, "tool", event.tool?.name || "Tool", event, {
        Input: event.tool?.input_summary || "No input summary",
      });
      openTools.set(event.tool?.call_id || event.event_id, span);
    }
    if (event.type === "tool_completed") {
      const span = openTools.get(event.tool?.call_id);
      if (span) {
        span.end = eventTime(event);
        span.state = "complete";
        span.metadata.Output = event.tool?.output_summary || "No output summary";
        openTools.delete(event.tool.call_id);
      }
    }
    if (event.type === "artifact_created") {
      const span = startSpan(record, "artifact", event.artifact?.title || "Artifact", event, {
        Kind: event.artifact?.kind || "artifact",
      });
      span.end = span.start;
      span.state = "complete";
    }
    if (event.type === "handoff_started" || event.type === "message_sent") {
      const target = records.get(event.target_agent_id)?.name || agents.get(event.target_agent_id)?.name || event.target_agent_id;
      const span = startSpan(record, event.type === "handoff_started" ? "handoff" : "message", target || "Another agent", event, {
        Target: target || "Unknown agent",
      });
      span.end = span.start;
      span.state = "complete";
    }
    if (event.type === "error") {
      const span = startSpan(record, "error", event.error?.code || "Error", event, {
        Message: event.error?.message || event.summary,
      });
      span.end = span.start;
      span.state = "error";
      record.state = "error";
    }
    if (event.type === "agent_completed") {
      record.end = eventTime(event);
      if (record.state !== "error") record.state = "complete";
    }
  });

  records.forEach((record) => {
    record.spans.forEach((span) => {
      if (!span.end) span.displayEnd = lastTime;
    });
  });
  return [...records.values()];
}

function appendTextElement(parent, tag, className, value) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  item.textContent = value;
  parent.append(item);
  return item;
}

function renderTrace() {
  const records = traceModel(observedEvents);
  if (!records.length) {
    traceSummary.textContent = observedEvents.length ? "Run started" : "Waiting for events";
    return;
  }

  traceList.innerHTML = "";
  records.forEach((record) => {
    const agentDetails = document.createElement("details");
    agentDetails.className = "trace-agent";
    agentDetails.open = record.state === "running" || record.state === "error";
    const summary = document.createElement("summary");
    appendTextElement(summary, "i", `trace-state ${record.state}`, "");
    appendTextElement(summary, "span", "", record.name);
    appendTextElement(summary, "time", "", formatDuration(record.start, record.end || eventTime(observedEvents[observedEvents.length - 1])));
    agentDetails.append(summary);

    const children = document.createElement("div");
    children.className = "trace-children";
    if (!record.spans.length) appendTextElement(children, "p", "empty-observability", "Waiting for agent activity.");
    record.spans.forEach((span) => {
      const spanDetails = document.createElement("details");
      spanDetails.className = "trace-span";
      const spanSummary = document.createElement("summary");
      appendTextElement(spanSummary, "span", "trace-kind", span.kind);
      appendTextElement(spanSummary, "span", "", span.label);
      appendTextElement(spanSummary, "time", "", formatDuration(span.start, span.end || span.displayEnd));
      spanDetails.append(spanSummary);
      const metadata = document.createElement("div");
      metadata.className = "trace-meta";
      Object.entries(span.metadata).forEach(([label, value]) => {
        const line = document.createElement("span");
        appendTextElement(line, "b", "", `${label}: `);
        line.append(document.createTextNode(String(value)));
        metadata.append(line);
      });
      if (Object.keys(span.metadata).length) spanDetails.append(metadata);
      children.append(spanDetails);
    });
    agentDetails.append(children);
    traceList.append(agentDetails);
  });

  const runStart = observedEvents.find((event) => event.type === "run_started");
  const latest = observedEvents[observedEvents.length - 1];
  const duration = runStart ? formatDuration(eventTime(runStart), eventTime(latest)) : "live";
  traceSummary.textContent = `${records.length} ${records.length === 1 ? "agent" : "agents"} · ${duration}`;
}

function metricTone(element, tone = "") {
  const card = element.closest("article");
  if (!card) return;
  card.classList.remove("good", "bad", "attention");
  if (tone) card.classList.add(tone);
}

function formatCount(value) {
  return new Intl.NumberFormat("en-US").format(value || 0);
}

function formatCost(value) {
  if (value === null) return "Cost not reported";
  if (value === 0) return "$0.00 reported cost";
  if (value < 0.01) return `$${value.toFixed(4)} reported cost`;
  return `$${value.toFixed(2)} reported cost`;
}

function renderScorecard() {
  const metrics = AgentariumRunMetrics.calculateRunMetrics(observedEvents);
  const complete = metrics.status === "succeeded" || metrics.status === "failed";
  const statusLabels = {
    waiting: "Waiting",
    running: "Running",
    succeeded: "Succeeded",
    failed: "Failed",
  };

  scorecardState.textContent = complete ? "Final metrics" : "Live metrics";
  metricStatus.textContent = statusLabels[metrics.status];
  metricStatusNote.textContent = complete
    ? `${metrics.errors} ${metrics.errors === 1 ? "error" : "errors"} observed`
    : "Workflow still running";
  metricTone(metricStatus, metrics.status === "succeeded" ? "good" : metrics.status === "failed" ? "bad" : "");

  metricDuration.textContent = metrics.durationMs ? formatDuration(0, metrics.durationMs) : "<10ms";
  metricTools.textContent = metrics.toolCalls ? `${metrics.toolsSucceeded}/${metrics.toolCalls}` : "No calls";
  metricToolsNote.textContent = metrics.toolCalls
    ? `${metrics.toolSuccessRate}% successful · ${metrics.toolsFailed} failed`
    : "No tool calls observed";
  metricTone(metricTools, !metrics.toolCalls || metrics.toolsFailed === 0 ? "good" : "attention");

  metricTokens.textContent = formatCount(metrics.totalTokens);
  metricCost.textContent = formatCost(metrics.costUsd);
  metricTasks.textContent = metrics.tasksStarted
    ? `${metrics.tasksCompleted}/${metrics.tasksStarted}`
    : "No tasks";
  metricRecovery.textContent = `${metrics.errors} / ${metrics.retries}`;
  metricTone(metricRecovery, metrics.errors ? "attention" : "good");

  metricBottleneck.textContent = metrics.bottleneck
    ? `${metrics.bottleneck.name} · ${formatDuration(0, metrics.bottleneck.durationMs)} longest active time`
    : "No task timing yet";
  if (metrics.loops.length) {
    const loop = metrics.loops[0];
    const agentName = agents.get(loop.agentId)?.name || loop.agentId || "Workflow";
    metricLoops.textContent = `${agentName} repeated ${loop.toolName} ${loop.count}× with the same input`;
  } else {
    metricLoops.textContent = "No repeated identical calls";
  }

  if (!complete) {
    executionScoreValue.textContent = "—";
    executionScore.style.setProperty("--score-angle", "0deg");
    executionScore.style.setProperty("--score-color", "#516a82");
    executionScore.setAttribute("aria-label", "Execution score available after the run");
    scoreVerdict.textContent = metrics.status === "running" ? "Run in progress" : "No run yet";
    scoreNote.textContent = "The final score appears when the workflow finishes.";
    return;
  }

  const score = metrics.score;
  let verdict = "Needs attention";
  let color = "#ff7f91";
  if (score >= 90) {
    verdict = "Clean execution";
    color = "#6ce7ae";
  } else if (score >= 75) {
    verdict = "Healthy with recovery";
    color = "#52dfd5";
  } else if (score >= 50) {
    verdict = "Recovery was costly";
    color = "#ffb86b";
  }
  executionScoreValue.textContent = String(score);
  executionScore.style.setProperty("--score-angle", `${score * 3.6}deg`);
  executionScore.style.setProperty("--score-color", color);
  executionScore.setAttribute("aria-label", `Execution score ${score} out of 100`);
  scoreVerdict.textContent = verdict;
  scoreNote.textContent = metrics.status === "failed"
    ? "The run failed. Other penalties show where execution also broke down."
    : "Score reflects completion, tool failures, errors, retries, and repeated identical calls.";
}

function storyElapsed(time, startTime) {
  if (!time || !startTime) return "Time not recorded";
  return `+${formatDuration(startTime, time)}`;
}

function storyMetaValue(label, value) {
  if (label === "Duration" && typeof value === "number") return formatDuration(0, value);
  if (label === "Tokens" && typeof value === "number") return formatCount(value);
  return String(value);
}

function sourceHost(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch (_error) {
    return url;
  }
}

function sourceLink(source, className = "story-source-link") {
  const link = document.createElement("a");
  link.className = className;
  link.href = source.url;
  link.target = "_blank";
  link.rel = "noreferrer noopener";
  link.textContent = source.title || sourceHost(source.url);
  link.title = source.url;
  return link;
}

function renderRunStory() {
  const story = AgentariumRunStory.buildRunStory(observedEvents);
  const complete = story.status === "succeeded" || story.status === "failed";
  const sourceByUrl = new Map(story.sources.map((source) => [source.url, source]));
  const previouslyOpen = new Set(
    [...storyAgents.querySelectorAll("details[open]")].map((item) => item.dataset.agent),
  );

  storyState.textContent = complete ? "Complete story" : story.status === "running" ? "Story building live" : "Waiting for a run";
  storyOverview.innerHTML = "";
  if (!observedEvents.length) {
    storyOverview.innerHTML = '<p class="empty-observability">Run a workflow to build its story.</p>';
    return;
  }

  const overviewMain = document.createElement("div");
  overviewMain.className = "story-overview-main";
  appendTextElement(
    overviewMain,
    "span",
    `story-status ${story.status}`,
    story.status === "succeeded" ? "Succeeded" : story.status === "failed" ? "Failed" : "Running",
  );
  appendTextElement(overviewMain, "strong", "", story.question);
  appendTextElement(
    overviewMain,
    "p",
    "",
    `${story.agents.length} ${story.agents.length === 1 ? "agent" : "agents"} · ${story.agents.reduce((sum, agent) => sum + agent.toolCalls, 0)} tool calls · ${story.sources.length} ${story.sources.length === 1 ? "source" : "sources"}`,
  );
  storyOverview.append(overviewMain);

  if (story.handoffs.length) {
    const path = document.createElement("div");
    path.className = "story-path";
    appendTextElement(path, "span", "", "Work moved");
    story.handoffs.forEach((handoff) => {
      appendTextElement(path, "strong", "", `${handoff.from} → ${handoff.to}`);
    });
    storyOverview.append(path);
  }

  storyAgents.innerHTML = "";
  story.agents.forEach((agent, index) => {
    const details = document.createElement("details");
    details.className = "story-agent";
    details.dataset.agent = agent.id;
    details.open = previouslyOpen.has(agent.id) || (!previouslyOpen.size && index === 0);
    const summary = document.createElement("summary");
    appendTextElement(summary, "span", "story-agent-number", String(index + 1).padStart(2, "0"));
    const title = document.createElement("div");
    appendTextElement(title, "h3", "", agent.name);
    appendTextElement(title, "p", "", agent.intent || "No task intent was recorded.");
    summary.append(title);
    appendTextElement(
      summary,
      "span",
      "story-agent-stats",
      `${agent.modelCalls} model · ${agent.toolCalls} tools · ${agent.sourceUrls.length} sources`,
    );
    details.append(summary);

    const steps = document.createElement("div");
    steps.className = "story-step-list";
    agent.steps.forEach((step) => {
      const item = document.createElement("article");
      item.className = `story-step ${step.tone}`;
      appendTextElement(item, "time", "", storyElapsed(step.time, story.startTime));
      const body = document.createElement("div");
      appendTextElement(body, "strong", "story-step-label", step.label);
      appendTextElement(body, "p", "story-step-detail", step.detail || "No detail recorded.");

      const visibleMeta = step.meta.filter(([, value]) => value !== null && value !== undefined && value !== "");
      if (visibleMeta.length) {
        const metadata = document.createElement("dl");
        metadata.className = "story-step-meta";
        visibleMeta.forEach(([label, value]) => {
          const row = document.createElement("div");
          appendTextElement(row, "dt", "", label);
          appendTextElement(row, "dd", "", storyMetaValue(label, value));
          metadata.append(row);
        });
        body.append(metadata);
      }

      if (step.sources.length) {
        const links = document.createElement("div");
        links.className = "story-step-sources";
        step.sources.forEach((url) => {
          const source = sourceByUrl.get(url);
          if (source) links.append(sourceLink(source));
        });
        body.append(links);
      }
      item.append(body);
      steps.append(item);
    });
    if (!agent.steps.length) appendTextElement(steps, "p", "empty-observability", "No agent activity recorded.");
    details.append(steps);
    storyAgents.append(details);
  });

  storyStepCount.textContent = `${story.timeline.length} ${story.timeline.length === 1 ? "step" : "steps"}`;
  storyTimeline.innerHTML = "";
  story.timeline.forEach((step) => {
    const item = document.createElement("li");
    appendTextElement(item, "time", "", storyElapsed(step.time, story.startTime));
    const copy = document.createElement("div");
    appendTextElement(copy, "span", "", step.agentName);
    appendTextElement(copy, "strong", "", step.label);
    appendTextElement(copy, "p", "", step.detail);
    item.append(copy);
    storyTimeline.append(item);
  });

  storySourceCount.textContent = `${story.sources.length} ${story.sources.length === 1 ? "source" : "sources"}`;
  storySourceList.innerHTML = "";
  if (!story.sources.length) {
    storySourceList.innerHTML = '<p class="empty-observability">No source links recorded in this run.</p>';
    return;
  }
  story.sources.forEach((source) => {
    const card = document.createElement("article");
    card.className = "source-card";
    appendTextElement(card, "span", "source-domain", sourceHost(source.url));
    card.append(sourceLink(source, "source-title"));
    if (source.snippet) appendTextElement(card, "p", "", source.snippet);
    appendTextElement(card, "small", "", `Used by ${source.agents.join(", ") || "the workflow"}`);
    storySourceList.append(card);
  });
}

function renderFlowMap() {
  const records = traceModel(observedEvents);
  flowMap.innerHTML = "";
  if (!records.length) return;

  const cards = document.createElement("div");
  cards.className = "flow-map-content";
  records.forEach((record, index) => {
    const card = document.createElement("article");
    card.className = "flow-node";
    appendTextElement(card, "span", "flow-node-number", `AGENT ${String(index + 1).padStart(2, "0")}`);
    appendTextElement(card, "h3", "", record.name);
    const facts = document.createElement("div");
    facts.className = "flow-facts";
    const tools = [...new Set(record.spans.filter((span) => span.kind === "tool").map((span) => span.label))];
    const artifacts = record.spans.filter((span) => span.kind === "artifact").length;
    const models = record.spans.filter((span) => span.kind === "model").length;
    tools.forEach((tool) => appendTextElement(facts, "span", "", `Tool · ${tool}`));
    if (models) appendTextElement(facts, "span", "", `${models} model ${models === 1 ? "call" : "calls"}`);
    if (artifacts) appendTextElement(facts, "span", "", `${artifacts} ${artifacts === 1 ? "artifact" : "artifacts"}`);
    if (!facts.children.length) appendTextElement(facts, "span", "", "Agent activity");
    card.append(facts);
    cards.append(card);
  });
  flowMap.append(cards);

  const relationships = observedEvents.filter((event) => event.type === "handoff_started" || event.type === "message_sent");
  const flowEvents = observedEvents.filter((event) => ["handoff_started", "message_sent", "error", "retrying"].includes(event.type));
  if (flowEvents.length) {
    const table = document.createElement("table");
    table.className = "flow-relation-table";
    const tableHead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    ["From", "Action", "To", "Details"].forEach((label) => {
      appendTextElement(headerRow, "th", "", label);
    });
    tableHead.append(headerRow);
    table.append(tableHead);

    const tableBody = document.createElement("tbody");
    flowEvents.forEach((event) => {
      const row = document.createElement("tr");
      appendTextElement(row, "td", "flow-relation-agent", agents.get(event.agent_id)?.name || event.agent_id);
      const action = {
        handoff_started: "Handoff",
        message_sent: "Message",
        error: "Error",
        retrying: "Retry",
      }[event.type] || event.type;
      appendTextElement(
        row,
        "td",
        `flow-relation-action ${event.type}`,
        action,
      );
      const target = event.target_agent_id
        ? agents.get(event.target_agent_id)?.name || event.target_agent_id
        : "—";
      appendTextElement(row, "td", "flow-relation-agent", target);
      const detailByType = {
        message_sent: event.metadata?.note || "Context shared before the next task.",
        handoff_started: "Responsibility moved to the next agent.",
        error: event.error?.message || "An observable workflow error occurred.",
        retrying: `Attempt ${event.metadata?.attempt || "in progress"} started.`,
      };
      const detail = detailByType[event.type] || event.summary;
      appendTextElement(row, "td", "flow-relation-detail", detail);
      tableBody.append(row);
    });
    table.append(tableBody);
    flowMap.append(table);
  }
  const errors = observedEvents.filter((event) => event.type === "error").length;
  const connectionLabel = `${relationships.length} ${relationships.length === 1 ? "connection" : "connections"}`;
  flowSummary.textContent = `${records.length} ${records.length === 1 ? "agent" : "agents"} · ${connectionLabel}${errors ? ` · ${errors} ${errors === 1 ? "error" : "errors"}` : ""}`;
}

function plainAction(event, record) {
  const name = record?.name || "The workflow";
  const target = agents.get(event.target_agent_id)?.name || event.target_agent_id || "the next agent";
  const tool = event.tool?.name || "a tool";
  const artifact = event.artifact?.title || "new work";
  const actions = {
    agent_spawned: `${name} joined the workflow.`,
    task_started: `${name} is deciding what to do next.`,
    model_started: `${name} is thinking about the next response.`,
    model_completed: `${name} finished thinking.`,
    tool_started: `${name} is using ${tool}.`,
    tool_completed: `${name} received results from ${tool}.`,
    artifact_created: `${name} saved ${artifact}.`,
    message_sent: `${name} sent information to ${target}.`,
    handoff_started: `${name} passed the work to ${target}.`,
    waiting: `${name} is waiting.`,
    retrying: `${name} is trying again.`,
    error: `${name} hit an error.`,
    task_completed: `${name} finished this step.`,
    agent_completed: `${name} finished its work.`,
  };
  return actions[event.type] || event.summary;
}

function renderInspector() {
  const record = selectedAgentId ? agents.get(selectedAgentId) : null;
  if (!record) return;
  inspectorTitle.textContent = record.name;
  inspectorHint.textContent = record.diagnostic?.label || `${partLabels[record.latestPart]} is active`;
  signalSymbol.textContent = partSymbols[record.latestPart];
  signalSource.textContent = `${record.name} · ${partLabels[record.latestPart]}`;
  signalMessage.textContent = record.latestAction;
  signalType.textContent = record.latestType;
  Object.entries(inspectorParts).forEach(([part, item]) => {
    item.classList.toggle("active", part === record.latestPart);
    const detail = record.details[part];
    const value = item.querySelector("strong");
    value.textContent = detail;
    value.title = detail;
  });
  Object.entries(inspectorStatusParts).forEach(([part, item]) => {
    item.classList.toggle("active", part === record.latestPart);
    item.classList.toggle("has-data", record.details[part] !== {
      head: "Nothing observed yet",
      hands: "Nothing observed yet",
      core: "Healthy · no errors",
      pack: "No artifacts yet",
      legs: "Waiting to start",
    }[part]);
  });
}

function selectAgent(agentId) {
  if (!agents.has(agentId)) return;
  selectedAgentId = agentId;
  agents.forEach(({ element }, id) => element.classList.toggle("selected", id === agentId));
  renderInspector();
}

function activateAvatar(event) {
  if (!event.agent_id) return;
  let record = agents.get(event.agent_id);
  if (!record) {
    record = registerAgent({ ...event, metadata: { name: event.agent_id } });
  }
  const avatar = record.element;
  const part = bodyPartByEvent[event.type] || "core";
  record.latestPart = part;
  record.details[part] = detailForEvent(event);
  record.latestAction = plainAction(event, record);
  record.latestType = event.type;

  agents.forEach(({ element }) => {
    element.classList.remove("active");
    element.querySelectorAll(".body-part").forEach((item) => {
      item.classList.remove("active", "ping");
    });
  });
  avatar.classList.add("active");
  const activePart = avatar.querySelector(`[data-part="${part}"]`);
  activePart?.classList.add("active", "ping", "has-data");
  applyDiagnosticState(record, event);
  showActivityCue(event, record);

  if (event.type === "agent_completed") {
    avatar.classList.remove("active");
    avatar.classList.toggle("complete", record.diagnostic.mode !== "error");
  }
  centerActiveAgent(record);
  selectAgent(event.agent_id);
}

function addEventRow(event) {
  document.querySelector(".empty-event")?.remove();
  const elapsed = Math.max(0, Math.floor((Date.now() - runStartedAt) / 1000));
  const row = document.createElement("li");
  row.className = "event-row";
  const time = document.createElement("time");
  time.className = "event-time";
  time.textContent = `+${String(elapsed).padStart(2, "0")}s`;
  const type = document.createElement("span");
  type.className = "event-type";
  type.textContent = event.type;
  const message = document.createElement("span");
  message.className = "event-message";
  message.textContent = event.summary;
  row.append(time, type, message);
  eventList.append(row);
  eventList.scrollTop = eventList.scrollHeight;
  eventCount.textContent = `${receivedEvents} ${receivedEvents === 1 ? "event" : "events"}`;
}

function showEvent(event) {
  if (event.type === "run_started" && event.run_id !== currentRunId) {
    currentRunId = event.run_id;
    resetView(event.metadata?.question || "Agent workflow");
    missionEyebrow.textContent = `Live run · ${event.run_id}`;
    runStartedAt = Date.now();
    runDot.className = "run-dot running";
    runLabel.textContent = "Signals live";
  }

  observedEvents.push(event);
  receivedEvents += 1;
  if (event.type === "agent_spawned") registerAgent(event);
  activateAvatar(event);
  showConnection(event);
  addEventRow(event);

  if (!event.agent_id) {
    const runFailed = event.type === "run_completed" && event.metadata?.status === "failed";
    signalSymbol.textContent = event.type === "run_completed" ? "✓" : "○";
    signalSource.textContent = "Workflow";
    signalMessage.textContent = event.type === "run_completed"
      ? (runFailed ? "The workflow finished with a failure." : "The workflow finished successfully.")
      : "The workflow is starting.";
    signalType.textContent = event.type;
    inspectorTitle.textContent = event.type === "run_completed"
      ? (runFailed ? "Failed" : "Complete")
      : "Starting";
    inspectorHint.textContent = "Live view";
    Object.values(inspectorStatusParts).forEach((item) => item.classList.remove("active"));
  }

  renderTrace();
  renderScorecard();
  renderRunStory();

  if (event.type === "run_completed") {
    runDot.className = event.metadata?.status === "failed" ? "run-dot failed" : "run-dot complete";
    runLabel.textContent = event.metadata?.status === "failed" ? "Run failed" : "Run complete";
    renderFlowMap();
  }
}

function processEventQueue() {
  if (playbackPaused || processingEvent || eventQueue.length === 0) return;
  processingEvent = true;
  const event = eventQueue.shift();
  showEvent(event);
  const delay = event.type === "run_started" ? 500 : 1400 / playbackSpeed;
  window.setTimeout(() => {
    processingEvent = false;
    processEventQueue();
  }, delay);
}

function enqueueEvent(event) {
  eventQueue.push(event);
  if (!playbackPaused && runLabel.textContent !== "Run complete") {
    runLabel.textContent = eventQueue.length > 1 ? `${eventQueue.length} events queued` : "Signals live";
  }
  processEventQueue();
}

resetView();
runButton.innerHTML = '<span aria-hidden="true">↻</span> Replay latest';
runButton.addEventListener("click", () => window.location.reload());
pauseButton.addEventListener("click", () => {
  playbackPaused = !playbackPaused;
  pauseButton.innerHTML = playbackPaused
    ? '<span aria-hidden="true">▶</span> Play'
    : '<span aria-hidden="true">Ⅱ</span> Pause';
  runLabel.textContent = playbackPaused ? `Paused · ${eventQueue.length} queued` : "Signals live";
  if (!playbackPaused) processEventQueue();
});
speedSelect.addEventListener("change", () => {
  playbackSpeed = Number(speedSelect.value) || 1;
});

const eventSource = new EventSource("/events");
eventTypes.forEach((eventType) => {
  eventSource.addEventListener(eventType, (message) => {
    try {
      enqueueEvent(JSON.parse(message.data));
    } catch (error) {
      console.error("Invalid Agentarium event", error);
    }
  });
});
eventSource.onerror = () => {
  if (runLabel.textContent !== "Run complete") {
    runDot.className = "run-dot";
    runLabel.textContent = "Reconnecting…";
  }
};
