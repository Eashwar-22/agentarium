'use strict';
const $ = id => document.getElementById(id);
const { buildRunView, stamp, eventPayload } = AgentariumRunView;
const palette = ['#658575','#7d8298','#a78a71','#708f9c','#a37e84','#8c9770','#9e936e','#7d8a95'];
const types = ['run_started','run_completed','agent_spawned','agent_completed','task_started','task_completed','model_started','model_completed','tool_started','tool_completed','artifact_created','message_sent','handoff_started','waiting','retrying','error'];
const labels = {run_started:'Run started',run_completed:'Run completed',agent_spawned:'Agent registered',agent_completed:'Agent completed',task_started:'Task started',task_completed:'Task completed',model_started:'Model request',model_completed:'Model response',tool_started:'Tool started',tool_completed:'Tool result',artifact_created:'Output saved',message_sent:'Message sent',handoff_started:'Work transferred',waiting:'Waiting',retrying:'Retry',error:'Error'};
let received = [], seen = new Set(), runId = null, visible = [], paused = false, replaying = false, replayTimer, view = buildRunView([]), modalEvent = null;
let renderTimer = null, tracePage = 0;
const PAGE_SIZE = 200;
function scheduleRender() { if (renderTimer === null) renderTimer = setTimeout(() => { renderTimer = null; render(); }, 100); }
function node(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
function remember(key,value) { try { if(value!==undefined)localStorage.setItem(key,value); return localStorage.getItem(key); } catch { return null; } }
document.documentElement.dataset.theme = remember('agentarium-theme') === 'dark' ? 'dark' : 'light';
function themeLabel() { $('theme').textContent=document.documentElement.dataset.theme==='dark'?'Light theme':'Dark theme'; }
themeLabel();
$('theme').onclick=()=>{document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark';remember('agentarium-theme',document.documentElement.dataset.theme);themeLabel();};
function duration(ms) { if(ms===null || !Number.isFinite(ms))return 'Not recorded'; return ms<1000 ? Math.round(ms)+' ms' : ms<60000 ? (ms/1000).toFixed(1)+' s' : Math.floor(ms/60000)+'m '+Math.round(ms%60000/1000)+'s'; }
function time(e) { return new Date(e.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
function kind(e) { return e.type==='error'?'Error':e.type==='retrying'?'Retry':e.type==='waiting'?'Waiting':e.tool?'Tool':e.type.startsWith('model')?'Model':e.artifact?'Output':e.type.includes('completed')?'Completed':e.type.startsWith('task')?'Task':'Event'; }
function badge(text) { return node('span',text,'badge '+text); }
function agent(e) { const a=view.agents.get(e.agent_id); const n=node('span',a?.name||'Workflow','agent'); n.style.setProperty('--agent',a?palette[a.index%palette.length]:'#78867b'); return n; }
function actionLabel(e) { return (labels[e.type]||e.type)+(e.tool?.name?' · '+e.tool.name.replaceAll('_',' '):e.artifact?.title?' · '+e.artifact.title:''); }
function empty(container,text) { container.replaceChildren(node('p',text,'empty')); }
function record(e,title,subtitle) {
  const b=node('button',undefined,'record'); b.type='button';
  const top=node('div',undefined,'record-top'); const left=node('div');left.append(badge(kind(e)),node('strong',title));top.append(left,agent(e));b.append(top);
  if(subtitle)b.append(node('p',subtitle));
  b.onclick=()=>openEvent(e); return b;
}
function render() {
  view=buildRunView(visible);
  $('question').textContent=view.start?.metadata?.question||'Your next run starts here';
  $('run-status').textContent=view.status; $('run-status').className='status '+view.status;
  $('run-id').textContent=view.start?.run_id||'No run received';
  $('run-context').textContent=replaying?'Replay · '+visible.length+' of '+received.length+' events':paused?'Display paused · '+(received.length-visible.length)+' new events waiting':view.end?'Finished '+new Date(view.end.timestamp).toLocaleString():visible.length?'Last recorded event '+new Date(visible.at(-1).timestamp).toLocaleString():'Start an instrumented workflow to see its recorded activity here.';
  $('trace-count').textContent=visible.length;
  $('active-count').textContent=view.active.length?view.active.length+' active':'';
  $('work-title').textContent=view.end?'Result':'In progress';
  const active=$('active-work');active.replaceChildren();
  if(view.end) {
    if(view.finalOutput) {
      const output=view.finalOutput.metadata?.full_output ?? view.finalOutput.artifact?.preview;
      if(output)active.append(node('pre',pretty(output),'result-text'));
      active.append(record(view.finalOutput,'View output details',view.finalOutput.artifact?.title));
    }
    else empty(active,view.status==='Failed'?'The run failed before an output was saved. Inspect errors below.':'The run completed without a saved output.');
  } else if(!view.active.length)empty(active,visible.length?'Waiting for the next action.':'Run a workflow with Agentarium to see its progress and results here.');
  else view.active.slice(0,20).forEach(c=>active.append(record(c.start,c.kind==='Tool'?c.start.tool.name.replaceAll('_',' '):c.kind==='Model'?'Open model request':'Open task',c.kind==='Tool'?c.start.metadata?.tool_description:view.agents.get(c.start.agent_id)?.description)));
  if(view.active.length>20)active.append(node('p','Showing 20 open operations. The Trace contains every recorded action.','empty'));
  const issues=$('issues');issues.replaceChildren();$('issue-count').textContent=view.issues.length;
  if(!view.issues.length)empty(issues,'No errors or retries.');
  else view.issues.slice(-6).reverse().forEach(e=>issues.append(record(e,(e.error?.code||labels[e.type]).replaceAll('_',' '),e.error?.message||e.summary)));
  const outputs=$('outputs');outputs.replaceChildren();$('output-count').textContent=view.outputs.length;
  if(!view.outputs.length)empty(outputs,'No outputs yet.');
  else [...view.outputs].reverse().slice(0,20).forEach(e=>outputs.append(record(e,e.artifact.title,view.agents.get(e.agent_id)?.description)));
  if(view.outputs.length>20)outputs.append(node('p','Showing the latest 20 outputs. Use the Trace output filter for the complete record.','empty'));
  const sources=$('sources');sources.replaceChildren();$('source-count').textContent=view.sources.length;
  if(!view.sources.length)empty(sources,'No sources for this run.');
  else view.sources.slice(0,100).forEach(s=>{const a=node('a',s.title||s.url,'source-link');a.href=s.url;a.target='_blank';a.rel='noopener noreferrer';a.append(node('small',new URL(s.url).hostname));sources.append(a);});
  if(view.sources.length>100)sources.append(node('p','Showing the first 100 sources. All recorded sources are available in the exported JSON.','empty'));
  const metrics=$('metrics');metrics.replaceChildren();
  const metric=(title,value,note)=>{const wrap=node('div');wrap.append(node('dt',title),node('dd',value));if(note)wrap.append(node('p',note,'metric-note'));metrics.append(wrap);};
  metric('Duration',duration(view.duration));
  metric('Agents',String(view.agents.size));
  metric('Tool calls',String(view.tools.total),view.tools.completed+' completed · '+view.tools.running+' open');
  metric('Tokens',view.tokens===null?'—':view.tokens.toLocaleString(),view.tokens===null?'Usage not reported':'Reported model usage');
  $('download').disabled=!visible.length;$('replay').disabled=!received.length;
  $('pause').textContent=paused?'Resume display':'Pause display';
  $('live').hidden=!replaying;
  const af=$('agent-filter'),selected=af.value;af.replaceChildren(new Option('All agents',''));view.agents.forEach(a=>af.add(new Option(a.name,a.id)));af.value=selected;
  renderTrace();
}
function renderTrace() {
  const list=$('trace-list'),scroll=list.scrollTop;
  const query=$('search').value.toLowerCase(),aid=$('agent-filter').value,type=$('type-filter').value;
  const filtered=view.events.filter(e=>(!aid||e.agent_id===aid)&&(!type||e.type.startsWith(type))&&(!query||[actionLabel(e),e.summary,view.agents.get(e.agent_id)?.name].join(' ').toLowerCase().includes(query)));
  tracePage=Math.min(tracePage,Math.max(0,Math.ceil(filtered.length/PAGE_SIZE)-1));
  list.replaceChildren();
  filtered.slice(tracePage*PAGE_SIZE,(tracePage+1)*PAGE_SIZE).forEach(e=>{const row=node('button',undefined,'trace-row');row.type='button';row.dataset.event=e.event_id;row.append(node('time',time(e)),agent(e));const action=node('span',undefined,'action');action.append(badge(kind(e)),document.createTextNode(actionLabel(e)));row.append(action);row.onclick=()=>openEvent(e);list.append(row);});
  if(!filtered.length)empty(list,view.events.length?'No actions match these filters.':'No actions recorded yet.');
  list.scrollTop=scroll;
  $('trace-footer').textContent=filtered.length+' matching actions · Page '+(tracePage+1)+' of '+Math.max(1,Math.ceil(filtered.length/PAGE_SIZE));
  $('trace-prev').disabled=tracePage===0;
  $('trace-next').disabled=(tracePage+1)*PAGE_SIZE>=filtered.length;
}
function pretty(value) { if(typeof value==='string'){try{return JSON.stringify(JSON.parse(value),null,2);}catch{return value;}}return JSON.stringify(value,null,2); }
function openEvent(e) {
  modalEvent=e;const m=e.metadata||{},call=view.calls.find(c=>c.start.event_id===e.event_id||c.end?.event_id===e.event_id);
  $('detail-title').textContent=actionLabel(e);$('detail-agent').textContent=(view.agents.get(e.agent_id)?.name||'Workflow')+' · '+time(e);$('copy-status').textContent='';
  const content=$('detail-content');content.replaceChildren();
  const field=(label,value)=>{if(value===undefined||value===null||value==='')return;const section=node('section',undefined,'field');section.append(node('h3',label),node('pre',pretty(value)));content.append(section);};
  const { input, output, intent, missingModelInput, previewOnly }=eventPayload(e,call);
  if(input!==undefined)field('Input',input);
  if(output!==undefined)field(previewOnly?'Recorded output preview':'Output',output);
  if(intent!==undefined)field('Task intent',intent);
  if(missingModelInput)content.prepend(node('p','The model call input was not captured in this recording. Task intent is shown separately.','payload-warning'));
  if(previewOnly)content.prepend(node('p','This recording contains a preview only. The full payload was not captured.','payload-warning'));
  field('Tool description',m.tool_description??call?.start.metadata?.tool_description);
  field('Agent description',m.description);
  if(call?.end)field('Call duration',duration(stamp(call.end)-stamp(call.start)));
  field('Error',e.error);
  const usage={};['model','input_tokens','output_tokens','total_tokens'].forEach(k=>{if(m[k]!==undefined)usage[k]=m[k];});if(Object.keys(usage).length)field('Model usage',usage);
  if(e.tool?.sources?.length)field('Sources',e.tool.sources);
  if(e.target_agent_id)field('Recipient',view.agents.get(e.target_agent_id)?.name||e.target_agent_id);
  if(input===undefined&&output===undefined&&!e.error)field('Recorded data',Object.keys(m).length?m:e.summary);
  const raw=node('details');const summary=node('summary','Raw event JSON');raw.append(summary);const block=node('section',undefined,'field');block.append(node('pre',JSON.stringify(e,null,2)));raw.append(block);content.append(raw);
  if(!$('detail-dialog').open)$('detail-dialog').showModal();content.scrollTop=0;
}
$('close-dialog').onclick=()=>$('detail-dialog').close();
$('detail-dialog').addEventListener('click',e=>{if(e.target===$('detail-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
function download(value,name) {const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('download').onclick=()=>download(visible,(runId||'run')+'.json');
$('download-detail').onclick=()=>{if(modalEvent)download(modalEvent,modalEvent.event_id+'.json');};
$('copy-detail').onclick=async()=>{try{await navigator.clipboard.writeText(JSON.stringify(modalEvent,null,2));$('copy-status').textContent='Copied';}catch{$('copy-status').textContent='Clipboard unavailable. Use Download JSON.';}};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{const trace=b.dataset.view==='trace';$('trace').hidden=!trace;$('overview').hidden=trace;document.querySelectorAll('[data-view]').forEach(n=>{n.classList.toggle('selected',n===b);n.setAttribute('aria-pressed',String(n===b));});});
['search','agent-filter','type-filter'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',()=>{tracePage=0;renderTrace();}));
$('trace-prev').onclick=()=>{tracePage--;renderTrace();$('trace-list').scrollTop=0;};
$('trace-next').onclick=()=>{tracePage++;renderTrace();$('trace-list').scrollTop=0;};
function returnLive() {clearTimeout(replayTimer);replaying=false;paused=false;visible=received;render();}
$('live').onclick=returnLive;
$('pause').onclick=()=>{paused=!paused;if(paused)visible=[...visible];else if(!replaying)visible=received;render();};
$('replay').onclick=()=>{clearTimeout(replayTimer);replaying=true;paused=false;visible=[];render();const snapshot=[...received];let index=0;function step(){if(!replaying)return;if(!paused&&index<snapshot.length){visible.push(snapshot[index++]);render();}if(index<snapshot.length)replayTimer=setTimeout(step,350);}step();};
function accept(e) {
  if(!e.event_id||!e.run_id||!Number.isFinite(Date.parse(e.timestamp))||seen.has(e.event_id))return;
  if(e.type==='run_started'&&runId!==e.run_id){clearTimeout(replayTimer);runId=e.run_id;received=[];visible=[];seen.clear();replaying=false;paused=false;$('detail-dialog').close();$('agent-filter').value='';}
  if(e.run_id!==runId)return;
  seen.add(e.event_id);received.push(e);if(!paused&&!replaying)visible=received;scheduleRender();
}
const stream=new EventSource('/events');
types.forEach(t=>stream.addEventListener(t,message=>{try{accept(JSON.parse(message.data));}catch(error){console.error('Unable to read workflow event',error);$('connection').textContent='An event could not be read';}}));
stream.onopen=()=>{$('connection').textContent='Connected';$('connection').dataset.state='connected';};
stream.onerror=()=>{$('connection').textContent='Reconnecting';$('connection').dataset.state='reconnecting';};
render();
