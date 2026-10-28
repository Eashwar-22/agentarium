const assert = require('node:assert/strict');
const { performance } = require('node:perf_hooks');
const { buildRunView } = require('../agentarium/static/run_view.js');
const events=[];
function add(type,fields={}) {events.push({sequence:events.length+1,event_id:String(events.length+1),type,timestamp:new Date(events.length*10).toISOString(),metadata:{},...fields});}
add('run_started');
for(let i=0;i<5000;i++) {
  const tool={name:'lookup',call_id:String(i)};
  add('tool_started',{agent_id:'a',tool,metadata:{tool_input_full:i.toString(36).padStart(4,'0').repeat(1024)}});
  add('tool_completed',{agent_id:'a',tool,metadata:{tool_output_full:i.toString(36).padStart(4,'0').repeat(1024)}});
}
add('run_completed',{metadata:{status:'succeeded'}});
const fixture=JSON.parse(JSON.stringify(events));
events.length=0;
const begin=performance.now();const view=buildRunView(fixture);const elapsed=performance.now()-begin;
const heapBytes=process.memoryUsage().heapUsed;
assert.equal(view.tools.completed,5000);assert.equal(view.active.length,0);
assert.ok(elapsed<1000,`10,002 events took ${elapsed.toFixed(1)}ms (target <1000ms)`);
assert.ok(heapBytes<256*1024*1024,`10,002 events used ${Math.round(heapBytes/1048576)} MiB heap (target <256 MiB)`);
console.log(JSON.stringify({events:fixture.length,model_ms:Number(elapsed.toFixed(2)),target_ms:1000,payload_bytes:5000*8192,heap_bytes:heapBytes,target_heap_bytes:256*1024*1024}));
