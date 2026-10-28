(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.AgentariumRunView = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const stamp = e => Date.parse(e?.timestamp) || 0;
  function buildRunView(input) {
    const events = [...input].sort((a, b) => a.sequence - b.sequence);
    const agents = new Map(), calls = new Map(), tasks = new Map(), modelQueues = new Map();
    const issues = [], outputs = [], sources = new Map();
    let tokens = 0, hasTokens = false, retries = 0;
    events.forEach(e => {
      if (e.agent_id && !agents.has(e.agent_id)) agents.set(e.agent_id, { id: e.agent_id, name: e.agent_id, description: '', index: agents.size });
      const agent = agents.get(e.agent_id);
      if (e.type === 'agent_spawned') Object.assign(agent, { name: e.metadata?.name || e.agent_id, description: e.metadata?.description || '' });
      if (e.type === 'task_started') tasks.set(`${e.agent_id}:${e.task_id}`, { event: e, active: true });
      if (e.type === 'task_completed') { const t = tasks.get(`${e.agent_id}:${e.task_id}`); if (t) t.active = false; }
      if (e.type === 'tool_started' || e.type === 'model_started') {
        const key = e.tool ? `tool:${e.agent_id}:${e.tool.call_id}` : `model:${e.agent_id}:${e.event_id}`;
        const call = { start: e, end: null, kind: e.tool ? 'Tool' : 'Model', status: 'Running' };
        calls.set(key, call);
        if (!e.tool) { const queue = modelQueues.get(e.agent_id) || []; queue.push(call); modelQueues.set(e.agent_id, queue); }
      }
      if (e.type === 'tool_completed' || e.type === 'model_completed') {
        const call = e.tool ? calls.get(`tool:${e.agent_id}:${e.tool.call_id}`) : modelQueues.get(e.agent_id)?.shift();
        if (call) { call.end = e; call.status = 'Completed'; }
      }
      if (e.type === 'error') {
        issues.push(e);
        // A workflow error is not evidence that every open tool failed.
        const call = e.metadata?.tool_call_id ? [...calls.values()].find(c => !c.end && c.start.agent_id === e.agent_id && c.start.tool?.call_id === e.metadata.tool_call_id) : null;
        if (call) { call.end = e; call.status = 'Error'; }
      }
      if (e.type === 'retrying') { retries++; issues.push(e); }
      if (e.type === 'artifact_created') outputs.push(e);
      if (e.type === 'model_completed' && e.metadata?.total_tokens !== undefined) { tokens += Number(e.metadata.total_tokens) || 0; hasTokens = true; }
      (e.tool?.sources || []).forEach(s => { try { const url = new URL(s.url); if (['http:', 'https:'].includes(url.protocol)) sources.set(s.url, s); } catch {} });
    });
    const start = events.find(e => e.type === 'run_started');
    const end = events.findLast(e => e.type === 'run_completed');
    const status = end ? (end.metadata?.status === 'failed' ? 'Failed' : 'Completed') : events.length ? 'Running' : 'Waiting';
    const active = [...calls.values()].filter(c => !c.end && !end);
    if (!end) tasks.forEach(t => {
      if (t.active && !active.some(c => c.start.agent_id === t.event.agent_id)) active.push({ start: t.event, end: null, kind: 'Task', status: 'Running' });
    });
    const tools = [...calls.values()].filter(c => c.kind === 'Tool');
    const finalId = end?.metadata?.final_artifact_id || end?.metadata?.result_artifact_id;
    const finalOutput = (finalId && outputs.find(e => e.artifact?.artifact_id === finalId)) || outputs.at(-1);
    return { events, agents, calls: [...calls.values()], active, issues, outputs, sources: [...sources.values()], start, end, status,
      tools: { completed: tools.filter(c => c.status === 'Completed').length, running: end ? 0 : tools.filter(c => !c.end).length, errors: tools.filter(c => c.status === 'Error').length, incomplete: end ? tools.filter(c => !c.end).length : 0, total: tools.length },
      tokens: hasTokens ? tokens : null, retries, finalOutput, duration: start ? Math.max(0, stamp(end || events.at(-1)) - stamp(start)) : null };
  }
  function eventPayload(event, call) {
    const m = event.metadata || {}, start = call?.start || event, end = call?.end || event;
    const model = event.type.startsWith('model');
    const input = model ? start.metadata?.model_input_full : (m.tool_input_full ?? start.metadata?.tool_input_full ?? event.tool?.input_summary ?? start.tool?.input_summary ?? m.activity_full ?? m.activity);
    const output = m.full_output ?? m.tool_output_full ?? m.model_output_full ?? end.metadata?.tool_output_full ?? end.metadata?.model_output_full ?? event.artifact?.preview ?? event.tool?.output_summary ?? end.tool?.output_summary;
    const fullOutput = m.full_output !== undefined || m.tool_output_full !== undefined || m.model_output_full !== undefined || end.metadata?.tool_output_full !== undefined || end.metadata?.model_output_full !== undefined;
    return { input, output, intent: model ? (start.metadata?.activity_full ?? start.metadata?.activity) : undefined,
      missingModelInput: model && input === undefined,
      previewOnly: output !== undefined && !fullOutput };
  }
  return { buildRunView, stamp, eventPayload };
});
