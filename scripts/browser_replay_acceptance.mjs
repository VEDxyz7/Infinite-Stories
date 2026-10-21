// Real headless Chrome/CDP UI acceptance. No provider keys or live-provider calls.
// Requires isolated Chrome on9223 and explicitly labelled loopback replay on8043.
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const backend=process.env.IS_BROWSER_API_ORIGIN || 'http://127.0.0.1:8043';
const web=process.env.IS_BROWSER_WEB_ORIGIN || 'http://127.0.0.1:8081';
const visual=process.env.IS_BROWSER_VISUAL_ARTIFACTS;
const replayCapabilities=await(await fetch(backend+'/v1/capabilities')).json();
if(replayCapabilities.verification_mode!=='captured_response_replay')throw Error('Refusing browser tests against a backend that is not explicitly captured-response replay');
const output=process.env.IS_BROWSER_REPORT || root+'reports/BROWSER_REPLAY_ACCEPTANCE_20261020.json';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let report={kind:'automated_real_chrome_webgl_captured_response_replay',new_live_qloo_requests:0,new_openai_requests:0,journeys:[],safari:{status:'BLOCKED',reason:'Built-in WebDriver rejects session: Allow remote automation is disabled. No security setting changed.'}};
try { report=JSON.parse(await fs.readFile(output,'utf8')); } catch {}
const seeds=[['artist','David Bowie'],['movie','Spirited Away'],['brand','LEGO'],['videogame','The Legend of Zelda: Breath of the Wild']];
const externalHosts=new Set();const runtimeExceptions=[];
async function connect(){
 const info=await(await fetch('http://127.0.0.1:9223/json/version')).json();
 report.chrome_version=info.Browser;
 const ws=new WebSocket(info.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});
 let serial=0;const waiting=new Map();
 ws.onmessage=event=>{const m=JSON.parse(event.data);if(visual&&m.method==='Network.requestWillBeSent'){try{const u=new URL(m.params.request.url);if(['http:','https:'].includes(u.protocol)&&!['127.0.0.1','localhost'].includes(u.hostname))externalHosts.add(u.hostname)}catch{}}if(visual&&m.method==='Runtime.exceptionThrown')runtimeExceptions.push(m.params.exceptionDetails.text);if(m.id){const p=waiting.get(m.id);if(!p)return;waiting.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++serial;waiting.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}))});
 return {send,ws};
}
if(visual&&process.env.IS_BROWSER_APPEND!=="1")report={kind:'actual_chrome_webgl_visual_replay',new_live_qloo_requests:0,new_openai_requests:0,journeys:[],safari:{status:'NOT_RUN',reason:'No new Safari execution in this visual pass'}};
const {send,ws}=await connect();
const chosen=process.argv[2];
try{
 for(const [category,name] of seeds.filter(([c])=>!chosen||chosen.split(',').includes(c))){
  report.journeys=report.journeys.filter(j=>j.category!==category);
  const entry={category,seed:name,status:'FAIL',checks:[]};report.journeys.push(entry);
  const {targetId}=await send('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  const cdp=(method,params)=>send(method,params,sessionId);
  const evaluate=async expression=>{const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value};
  const view=()=>evaluate('typeof current!=="undefined" && current ? JSON.parse(JSON.stringify(current)) : null');
  async function until(fn,label,timeout=20000){const end=Date.now()+timeout;while(Date.now()<end){const result=await fn();if(result)return result;await sleep(100)}throw Error('Timeout: '+label)}
  async function click(command){await until(()=>evaluate(`(()=>{const b=document.querySelector('button[data-command="${command}"]');if(!b||b.disabled)return false;b.click();return true})()`),'enabled '+command)}
  async function idle(){return until(async()=>{const v=await view();return v&&!v.busy&&!v.pending?v:null},'confirmed state')}
  async function move(x,y){
   for(const [axis,target] of [['y',8],['x',x],['y',y]]){
    for(let n=0;n<40;n++){
     const v=await idle();const delta=target-v[axis];if(Math.abs(delta)<.65)break;
     const command=axis==='x'?(delta>0?'east':'west'):(delta>0?'north':'south');
     await click(command);
     await until(async()=>{const next=await view();return next&&!next.busy&&!next.pending&&Math.abs(next[axis]-v[axis])>.2},'physics/autosave '+command,10000);
     if(n===39)throw Error('Movement did not converge');
    }
   }
  }
  async function screenshot(name){
   if(!visual)return;await sleep(400);await fs.mkdir(visual,{recursive:true});
   const r=await cdp('Page.captureScreenshot',{format:'png'});await fs.writeFile(visual+'/'+category+'-'+name+'.png',Buffer.from(r.data,'base64'));
  }
  async function choose(prefix){
   const v=await idle();const a=v.actions.find(a=>a.command.startsWith(prefix));
   if(!a)throw Error('Expected nearby allowed choice missing: '+prefix);
   await click(a.command);await until(async()=>{const n=await view();return n&&n.revision>v.revision&&!n.busy},'choice confirmation');
  }
  try{
   await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Network.enable');await cdp('Network.setCacheDisabled',{cacheDisabled:true});
   await cdp('Page.navigate',{url:web});
   await until(()=>evaluate('typeof player!=="undefined" && !!player && !!current && current.cultural_available'),'Unity ready',90000);
   const label=await evaluate('document.querySelector("#status").textContent');if(!label.includes('LOCAL CAPTURE REPLAY'))throw Error('Missing replay attribution');
   await evaluate(`(()=>{document.querySelector('#culture-seed').value=${JSON.stringify(name)};document.querySelector('#culture-category').value=${JSON.stringify(category)};document.querySelector('#culture-form').requestSubmit();})()`);
   await click('cultural');
   await until(async()=>{const v=await view();return v&&(!v.title||v.actions.some(a=>a.command.startsWith('confirm:')))},'resolution');
   let expectedSeedName=name;
   let v=await view();if(v.title){const a=v.actions.find(a=>a.label.includes('The Lego Group'));if(!a)throw Error('Expected canonical brand missing');expectedSeedName=a.label.slice('Confirm: '.length).split(' · ')[0];await click(a.command);entry.checks.push('confirmed actual returned canonical brand')}
   await until(async()=>{const v=await view();return v&&!v.title&&!v.busy},'created world');
   v=await idle();if(!v.objectives.some(t=>t.includes('cultural memory')))throw Error('Cultural quest absent');entry.checks.push('cultural context creates required objective');
   if(visual){
    await screenshot('record-bar');
    await click('scanner');await until(async()=>(await view()).panel==='scanner','Scanner actual UI');await screenshot('scanner');if(!(await view()).panel_text?.includes('SEED · '+expectedSeedName+' ['+category+']'))throw Error('Scanner lost actual saved seed');
    const revision=(await view()).revision;await click('compare');await until(async()=>(await view()).panel_text?.includes('AUTHORED CONTROL'),'honest authored comparison');await screenshot('authored-control');if((await view()).revision!==revision)throw Error('Read-only comparison mutated state');
    await click('continue');await click('journal');await until(async()=>(await view()).panel==='journal','Journal actual UI');await screenshot('journal');if(!(await view()).panel_text?.includes('CONFIRMED OBJECTIVES'))throw Error('Journal missing confirmed objectives');await click('continue');
    entry.checks.push('actual Scanner, authored-control comparison and confirmed Journal open; comparison preserves revision');
   }
   // Unsupported browser command must not bypass client or authoritative progression.
   const before=v.revision;await evaluate(`player.SendMessage('Infinite Stories','OnBrowserCommand','choose:cultural_echo_0:fabricated')`);await sleep(250);
   if((await view()).revision!==before)throw Error('Fabricated answer changed progress');entry.checks.push('unsupported browser answer leaves revision unchanged');
   for(let stage=0;stage<4;stage++){
    if(stage===2){await move(12,6);await choose('choose:cultural_echo_0:');entry.checks.push('actual cultural card completed through controller and server rules')}
    await move(13,9);
    if(visual){await click('interact');await until(async()=>(await view()).panel==='dialogue','dialogue UI');await screenshot(['record-bar-dialogue','cinema-dialogue','boutique-dialogue','gate-dialogue'][stage]);await click('continue');}
    await choose(['choose:mara:take_map','choose:ivo:learn_rhythm','choose:sera:promise_guard','choose:beacon:light_together'][stage]);
    if(stage<3){await move(29,8);await choose('travel:');await until(async()=>{const v=await view();return v.visits===stage+2&&!v.busy},'area transition')}
    console.log(JSON.stringify({category,milestone:'stage '+(stage+1)}));
   }
   v=await idle();if(v.ending!=='together'||v.visits!==4||!v.objectives.every(t=>t.startsWith('Complete:')))throw Error('Invalid ending/objectives');
   entry.checks.push('four-area quest and ending completed');const rev=v.revision;const goals=v.objectives;
   await screenshot('taste-card');
   await cdp('Page.captureScreenshot',{format:'png'}).then(async r=>{await fs.mkdir((visual || root+'reports/local/browser-acceptance'),{recursive:true});await fs.writeFile((visual || root+'reports/local/browser-acceptance')+'/chrome-'+category+'.png',Buffer.from(r.data,'base64'))});
   await cdp('Page.reload',{ignoreCache:true});
   await until(()=>evaluate('typeof player!=="undefined" && !!player && !!current'),'reloaded Unity',90000);
   await click('resume');await until(async()=>{const v=await view();return v&&!v.title&&v.ending==='together'},'resume ending');
   const resumed=await idle();if(resumed.revision!==rev||JSON.stringify(resumed.objectives)!==JSON.stringify(goals))throw Error('Resume changed progress');
   entry.checks.push('page refresh/resume preserves exact revision and completed objectives without duplication');entry.ending=resumed.ending;entry.visits=resumed.visits;entry.revision=resumed.revision;entry.status='PASS';
  }catch(error){entry.error=error.message;entry.last_public_view=await view().catch(()=>null)}
  if(visual){report.non_loopback_browser_hosts=[...externalHosts];report.browser_runtime_exceptions=runtimeExceptions;}
  await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({category,status:entry.status,error:entry.error}));
  await send('Target.closeTarget',{targetId});
 }
}finally{ws.close(); if(report.journeys.some(j=>j.status!=='PASS'))process.exitCode=1;}
