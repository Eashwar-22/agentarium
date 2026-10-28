const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const puppeteer = require('puppeteer');

test('dashboard browser regressions', { timeout: 60000 }, async t => {
  let sequence = 0;
  const event = (type, fields={}) => ({ event_id: String(++sequence), sequence, run_id:'browser-fixture', type, timestamp:new Date(sequence*1000).toISOString(), metadata:{}, ...fields });
  const fullInput = JSON.stringify({ input_items:[{ role:'user', content:'x'.repeat(8000)+'INPUT_END' }] });
  const fullOutput = JSON.stringify({ result:'y'.repeat(8000)+'OUTPUT_END' });
  const events = [event('run_started',{metadata:{question:'Browser fixture'}}),event('agent_spawned',{agent_id:'a',metadata:{name:'Coordinator'}}),event('agent_spawned',{agent_id:'b',metadata:{name:'Writer'}}),event('model_started',{agent_id:'a',metadata:{model_input_full:fullInput,activity_full:'Task intent'}}),event('model_completed',{agent_id:'a',metadata:{model_output_full:'response'}}),event('artifact_created',{agent_id:'a',artifact:{artifact_id:'draft',kind:'answer',title:'Draft'},metadata:{full_output:'Earlier draft'}}),event('artifact_created',{agent_id:'b',artifact:{artifact_id:'final',kind:'report',title:'Final JSON'},metadata:{full_output:fullOutput}})];
  const clients=new Set();
  const wire=e=>`id: ${e.event_id}\nevent: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`;
  const server=http.createServer(async(req,res)=>{
    if(req.url==='/events') {
      res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache'});
      events.forEach(e=>res.write(wire(e)));clients.add(res);req.on('close',()=>clients.delete(res));return;
    }
    const filename=new URL(req.url,'http://localhost').pathname;
    const names={'/':'index.html','/script.js':'script.js','/run_view.js':'run_view.js','/styles.css':'styles.css'};
    if(!names[filename]) {res.writeHead(404).end();return;}
    const ext=path.extname(names[filename]);res.setHeader('Content-Type',ext==='.js'?'text/javascript':ext==='.css'?'text/css':'text/html');
    res.end(await fs.readFile(path.join(__dirname,'../../agentarium/static',names[filename])));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    const options={headless:true};
    if(process.env.CHROME_PATH)options.executablePath=process.env.CHROME_PATH;
    else if(process.platform==='darwin')options.executablePath='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
    browser=await puppeteer.launch(options);
    const page=await browser.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`,{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.getElementById('trace-count').textContent==='7');

    await t.test('filters and modal preserve full paired model input',async()=>{
      await page.click('[data-view="trace"]');
      await page.select('#agent-filter','a');await page.select('#type-filter','model');
      assert.equal(await page.$$eval('.trace-row',rows=>rows.length),2);
      await page.click('[data-event="5"]');
      await page.waitForSelector('dialog[open]');
      const text=await page.$eval('#detail-content',n=>n.textContent);
      assert.ok(text.includes('INPUT_END'));assert.ok(text.includes('Task intent'));
      assert.ok(await page.$eval('.dialog-content',n=>n.scrollHeight>n.clientHeight));
      await page.keyboard.press('Escape');
      assert.equal(await page.$eval('dialog',n=>n.open),false);
      await page.select('#type-filter','');await page.select('#agent-filter','');
      await page.type('#search','Final JSON');
      assert.equal(await page.$$eval('.trace-row',rows=>rows.length),1);
      await page.click('[data-event="7"]');
      assert.ok((await page.$eval('#detail-content',n=>n.textContent)).includes('OUTPUT_END'));
      await page.click('#close-dialog');
      await page.$eval('#search',n=>{n.value='';n.dispatchEvent(new Event('input'));});
    });
    await t.test('pause buffers new data and resume selects the final structured artifact',async()=>{
      await page.click('#pause');
      const end=event('run_completed',{metadata:{status:'succeeded',final_artifact_id:'final'}});events.push(end);clients.forEach(res=>res.write(wire(end)));
      await page.waitForFunction(()=>document.getElementById('run-context').textContent.includes('1 new events'));
      assert.equal(await page.$eval('#trace-count',n=>n.textContent),'7');
      await page.click('#pause');
      assert.equal(await page.$eval('#run-status',n=>n.textContent),'Completed');
      await page.click('[data-view="overview"]');
      assert.ok((await page.$eval('.result-text',n=>n.textContent)).includes('OUTPUT_END'));
    });
    await t.test('theme persists and mobile layout does not overflow',async()=>{
      await page.click('#theme');
      assert.equal(await page.$eval('html',n=>n.dataset.theme),'dark');
      await page.reload({waitUntil:'domcontentloaded'});
      await page.waitForFunction(()=>document.getElementById('trace-count').textContent==='8');
      assert.equal(await page.$eval('html',n=>n.dataset.theme),'dark');
      await page.setViewport({width:390,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
      await page.click('[data-view="trace"]');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    });
    await t.test('a larger run is paginated and replay can return to live data',async()=>{
      await page.setViewport({width:1280,height:900});
      let seq=0;
      const large=(type,fields={})=>({event_id:'large-'+(++seq),sequence:seq,run_id:'large-fixture',type,timestamp:new Date(seq*1000).toISOString(),metadata:{},...fields});
      const batch=[large('run_started',{metadata:{question:'Large fixture'}}),large('agent_spawned',{agent_id:'a',metadata:{name:'Coordinator'}})];
      for(let i=0;i<250;i++) {
        const tool={name:'lookup_'+i,call_id:String(i)};
        batch.push(large('tool_started',{agent_id:'a',tool}),large('tool_completed',{agent_id:'a',tool}));
      }
      batch.push(large('run_completed',{metadata:{status:'succeeded'}}));
      events.push(...batch);clients.forEach(res=>batch.forEach(e=>res.write(wire(e))));
      await page.waitForFunction(()=>document.getElementById('trace-count').textContent==='503');
      assert.equal(await page.$$eval('.trace-row',rows=>rows.length),200);
      await page.click('#trace-next');
      assert.ok((await page.$eval('#trace-footer',n=>n.textContent)).includes('Page 2 of 3'));
      await page.type('#search','lookup 249');
      assert.equal(await page.$$eval('.trace-row',rows=>rows.length),2);
      await page.click('#replay');
      assert.equal(await page.$eval('#trace-count',n=>n.textContent),'1');
      await page.click('#live');
      assert.equal(await page.$eval('#trace-count',n=>n.textContent),'503');
    });
    assert.deepEqual(errors,[]);
  } finally {
    if(browser)await browser.close();
    clients.forEach(res=>res.end());server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
  }
});
