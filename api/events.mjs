const RUN_ID = "run-vercel-demo-001";
const STARTED_AT = Date.UTC(2026, 8, 11, 12, 0, 0);

function buildDemoEvents() {
  const events = [];

  function emit(type, summary, details = {}) {
    const sequence = events.length + 1;
    events.push({
      schema_version: "0.2",
      run_id: RUN_ID,
      event_id: "demo-event-" + String(sequence).padStart(3, "0"),
      sequence,
      timestamp: new Date(STARTED_AT + (sequence - 1) * 1500).toISOString(),
      type,
      summary,
      metadata: {},
      ...details,
    });
  }

  emit("run_started", "Customer-support research run started.", {
    metadata: {
      demo: true,
      question: "Should a small online shop adopt an AI customer-support agent?",
    },
  });

  for (const [agentId, name] of [
    ["planner", "Planner"],
    ["researcher", "Researcher"],
    ["reviewer", "Evidence Reviewer"],
    ["writer", "Brief Writer"],
  ]) {
    emit("agent_spawned", name + " joined the run.", {
      agent_id: agentId,
      metadata: { name, role: name },
    });
  }

  emit("task_started", "Planner started defining the decision criteria.", {
    agent_id: "planner",
    task_id: "task-plan",
    metadata: { activity: "Define cost, quality, and implementation checks." },
  });
  emit("model_started", "Planner is creating a research plan.", {
    agent_id: "planner",
    task_id: "task-plan",
    metadata: { activity: "Create a decision-focused research plan.", input_items: 1, model: "gpt-demo" },
  });
  emit("model_completed", "Planner received a structured plan.", {
    agent_id: "planner",
    task_id: "task-plan",
    metadata: { output_items: 1, input_tokens: 310, output_tokens: 126, total_tokens: 436 },
  });
  const plan = {
    artifact_id: "artifact-plan",
    kind: "plan",
    title: "Support-agent evaluation plan",
    preview: "Compare customer impact, operational risk, and rollout cost.",
  };
  emit("artifact_created", "Planner saved the evaluation plan.", {
    agent_id: "planner",
    task_id: "task-plan",
    artifact: plan,
  });
  emit("message_sent", "Planner sent the research brief to Researcher.", {
    agent_id: "planner",
    target_agent_id: "researcher",
    metadata: { message: "Find credible evidence about adoption, risk, and human oversight." },
  });
  emit("task_completed", "Planner completed the research plan.", {
    agent_id: "planner",
    task_id: "task-plan",
  });
  emit("agent_completed", "Planner finished its assigned work.", { agent_id: "planner" });

  emit("task_started", "Researcher started gathering evidence.", {
    agent_id: "researcher",
    task_id: "task-research",
    metadata: { activity: "Find evidence about AI customer-support systems." },
  });
  emit("tool_started", "Researcher started web_search.", {
    agent_id: "researcher",
    task_id: "task-research",
    tool: {
      name: "web_search",
      call_id: "search-001",
      input_summary: "AI customer support benefits risks human oversight",
      sources: [],
    },
  });
  emit("tool_completed", "The search returned two useful guidance pages.", {
    agent_id: "researcher",
    task_id: "task-research",
    tool: {
      name: "web_search",
      call_id: "search-001",
      output_summary: "Two relevant sources found.",
      sources: [
        {
          title: "NIST AI Risk Management Framework",
          url: "https://www.nist.gov/itl/ai-risk-management-framework",
          snippet: "Framework for managing risks in the design and use of AI systems.",
        },
        {
          title: "OECD AI Principles",
          url: "https://oecd.ai/en/ai-principles",
          snippet: "Principles covering trustworthy AI and accountability.",
        },
      ],
    },
  });
  const firstEvidence = {
    artifact_id: "artifact-first-evidence",
    kind: "source_bundle",
    title: "Initial support-agent evidence",
    preview: "General AI risk guidance and oversight principles.",
  };
  emit("artifact_created", "Researcher saved the initial evidence bundle.", {
    agent_id: "researcher",
    task_id: "task-research",
    artifact: firstEvidence,
  });
  emit("handoff_started", "Researcher handed evidence to Evidence Reviewer.", {
    agent_id: "researcher",
    target_agent_id: "reviewer",
    artifact: firstEvidence,
  });
  emit("waiting", "Researcher waited for the evidence review.", {
    agent_id: "researcher",
    task_id: "task-research",
    metadata: { waiting_for: "reviewer" },
  });

  emit("task_started", "Evidence Reviewer started checking the sources.", {
    agent_id: "reviewer",
    task_id: "task-review",
    metadata: { activity: "Check whether the evidence supports a buying decision." },
  });
  emit("error", "The evidence lacked customer-service-specific benchmarks.", {
    agent_id: "reviewer",
    task_id: "task-review",
    error: {
      code: "evidence_gap",
      message: "The first search found general guidance but no support-specific benchmark.",
      retryable: true,
    },
  });
  emit("message_sent", "Evidence Reviewer requested one focused follow-up search.", {
    agent_id: "reviewer",
    target_agent_id: "researcher",
    metadata: { message: "Find a support-specific benchmark and keep the recommendation cautious." },
  });
  emit("retrying", "Researcher started a focused second search.", {
    agent_id: "researcher",
    task_id: "task-research",
    metadata: { attempt: 2, retry_budget_remaining: 0 },
  });
  emit("tool_started", "Researcher started the follow-up web_search.", {
    agent_id: "researcher",
    task_id: "task-research",
    tool: {
      name: "web_search",
      call_id: "search-002",
      input_summary: "customer service AI benchmark human escalation",
      sources: [],
    },
  });
  emit("tool_completed", "The follow-up search found a support benchmark.", {
    agent_id: "researcher",
    task_id: "task-research",
    tool: {
      name: "web_search",
      call_id: "search-002",
      output_summary: "One support-specific report found.",
      sources: [
        {
          title: "Generative AI at Work",
          url: "https://www.nber.org/papers/w31161",
          snippet: "A field study of AI assistance used by 5,179 customer-support agents.",
        },
      ],
    },
  });
  const acceptedEvidence = {
    artifact_id: "artifact-accepted-evidence",
    kind: "evidence_bundle",
    title: "Reviewed support-agent evidence",
    preview: "Use a limited pilot, measure resolution quality, and retain human escalation.",
  };
  emit("artifact_created", "Researcher saved the revised evidence bundle.", {
    agent_id: "researcher",
    task_id: "task-research",
    artifact: acceptedEvidence,
  });
  emit("task_completed", "Researcher completed the evidence search.", {
    agent_id: "researcher",
    task_id: "task-research",
  });
  emit("agent_completed", "Researcher finished its assigned work.", { agent_id: "researcher" });
  emit("task_completed", "Evidence Reviewer accepted the revised evidence.", {
    agent_id: "reviewer",
    task_id: "task-review",
  });
  emit("handoff_started", "Evidence Reviewer handed approved evidence to Brief Writer.", {
    agent_id: "reviewer",
    target_agent_id: "writer",
    artifact: acceptedEvidence,
  });
  emit("agent_completed", "Evidence Reviewer finished its assigned work.", { agent_id: "reviewer" });

  emit("task_started", "Brief Writer started the recommendation.", {
    agent_id: "writer",
    task_id: "task-write",
    metadata: { activity: "Write a short decision brief from approved evidence." },
  });
  emit("model_started", "Brief Writer is drafting the final brief.", {
    agent_id: "writer",
    task_id: "task-write",
    metadata: { activity: "Draft the recommendation.", input_items: 3, model: "gpt-demo" },
  });
  emit("model_completed", "Brief Writer received the completed draft.", {
    agent_id: "writer",
    task_id: "task-write",
    metadata: { output_items: 1, input_tokens: 842, output_tokens: 288, total_tokens: 1130 },
  });
  const answer = {
    artifact_id: "artifact-answer",
    kind: "answer",
    title: "AI support-agent decision brief",
    preview: "Run a narrow pilot first. Keep human escalation, log failures, and compare quality against the current process before expanding.",
  };
  emit("artifact_created", "Brief Writer saved the final recommendation.", {
    agent_id: "writer",
    task_id: "task-write",
    artifact: answer,
  });
  emit("task_completed", "Brief Writer completed the recommendation.", {
    agent_id: "writer",
    task_id: "task-write",
  });
  emit("agent_completed", "Brief Writer finished its assigned work.", { agent_id: "writer" });
  emit("run_completed", "The decision-support run completed successfully.", {
    metadata: { demo: true, status: "succeeded", result_artifact_id: answer.artifact_id },
  });

  return events;
}

export const demoEvents = buildDemoEvents();

export function GET() {
  const body = ["retry: 60000", ""]
    .concat(demoEvents.flatMap((event) => [
      "id: " + event.event_id,
      "event: " + event.type,
      "data: " + JSON.stringify(event),
      "",
    ]))
    .join("\n");

  return new Response(body, {
    headers: {
      "Cache-Control": "no-cache, no-transform",
      "Content-Type": "text/event-stream; charset=utf-8",
    },
  });
}
