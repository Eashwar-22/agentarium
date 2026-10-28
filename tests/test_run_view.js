const test = require('node:test');
const assert = require('node:assert/strict');
const { buildRunView } = require('../agentarium/static/run_view.js');
const { eventPayload } = require('../agentarium/static/run_view.js');
function event(sequence, type, fields = {}) {
  return { sequence, event_id: String(sequence), timestamp: new Date(sequence * 1000).toISOString(), type, metadata: {}, ...fields };
}
test('an open tool stays running instead of being counted as failed', () => {
  const events = [event(1, 'run_started'), event(2, 'tool_started', { agent_id: 'a', tool: { name: 'lookup', call_id: '1' } })];
  assert.deepEqual(buildRunView(events).tools, { total: 1, running: 1, completed: 0, errors: 0, incomplete: 0 });
  events.push(event(3, 'tool_completed', { agent_id: 'a', tool: { name: 'lookup', call_id: '1' } }));
  assert.equal(buildRunView(events).active.length, 0);
  assert.equal(buildRunView(events).tools.completed, 1);
});
test('parallel calls are paired by agent and call ID', () => {
  const events = [event(1,'run_started'), event(2,'tool_started',{agent_id:'a',tool:{call_id:'x'}}), event(3,'tool_started',{agent_id:'b',tool:{call_id:'x'}}), event(4,'tool_completed',{agent_id:'b',tool:{call_id:'x'}})];
  const view = buildRunView(events);
  assert.equal(view.active[0].start.agent_id, 'a');
  assert.equal(view.calls[1].status, 'Completed');
});
test('an agent error does not invent a tool failure without a call ID', () => {
  const view = buildRunView([event(1,'run_started'),event(2,'tool_started',{agent_id:'a',tool:{call_id:'x'}}),event(3,'error',{agent_id:'a'}),event(4,'run_completed',{metadata:{status:'failed'}})]);
  assert.equal(view.tools.errors,0);
  assert.equal(view.tools.incomplete,1);
});
test('a finished run has no active work and preserves a complete output', () => {
  const payload = JSON.stringify({ text: 'x'.repeat(5000) });
  const view = buildRunView([event(1,'run_started'),event(2,'model_started',{agent_id:'a'}),event(3,'artifact_created',{agent_id:'a',artifact:{kind:'answer'},metadata:{full_output:payload}}),event(4,'run_completed',{metadata:{status:'succeeded'}})]);
  assert.equal(view.active.length,0);
  assert.equal(view.finalOutput.metadata.full_output,payload);
  assert.equal(view.status,'Completed');
  assert.equal(view.tokens,null);
});
test('retry history remains visible after successful completion', () => {
  const view=buildRunView([event(1,'run_started'),event(2,'error',{agent_id:'a',error:{code:'timeout'}}),event(3,'retrying',{agent_id:'a'}),event(4,'run_completed',{metadata:{status:'succeeded'}})]);
  assert.equal(view.status,'Completed');
  assert.equal(view.issues.length,2);
  assert.equal(view.retries,1);
});
test('the latest structured output wins over an earlier text draft', () => {
  const view=buildRunView([event(1,'run_started'),event(2,'artifact_created',{artifact:{kind:'answer',artifact_id:'draft'}}),event(3,'artifact_created',{artifact:{kind:'reviewdecision',artifact_id:'final'}}),event(4,'run_completed')]);
  assert.equal(view.finalOutput.artifact.artifact_id,'final');
});
test('an explicit final artifact reference takes precedence', () => {
  const view=buildRunView([event(1,'artifact_created',{artifact:{artifact_id:'chosen'}}),event(2,'artifact_created',{artifact:{artifact_id:'other'}}),event(3,'run_completed',{metadata:{final_artifact_id:'chosen'}})]);
  assert.equal(view.finalOutput.artifact.artifact_id,'chosen');
});
test('legacy model activity is shown as task intent instead of model input', () => {
  const payload=eventPayload(event(1,'model_started',{metadata:{activity_full:'Original task'}}));
  assert.equal(payload.input,undefined);
  assert.equal(payload.intent,'Original task');
  assert.equal(payload.missingModelInput,true);
});
test('model responses show the paired call input with tool results', () => {
  const input=JSON.stringify([{type:'function_call_output',output:'New evidence'}]);
  const start=event(1,'model_started',{metadata:{model_input_full:input}});
  const end=event(2,'model_completed',{metadata:{model_output_full:'complete response'}});
  const payload=eventPayload(end,{start,end});
  assert.equal(payload.input,input);
  assert.equal(payload.output,'complete response');
  assert.equal(payload.previewOnly,false);
});
