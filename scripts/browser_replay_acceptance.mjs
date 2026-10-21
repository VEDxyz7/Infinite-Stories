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
const playerPresentation=process.env.IS_BROWSER_PLAYER_PRESENTATION==='1';
const investigation=process.env.IS_BROWSER_INVESTIGATION==='1';
const phase2b=process.env.IS_BROWSER_PHASE2B==='1';const modelReplies=[];const requestMethods=new Map();
const externalHosts=new Set();const runtimeExceptions=[];
async function connect(){
 const info=await(await fetch('http://127.0.0.1:9223/json/version')).json();
 report.chrome_version=info.Browser;
 const ws=new WebSocket(info.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});
 let serial=0;const waiting=new Map();
 ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.method==='Network.requestWillBeSent')requestMethods.set(m.params.requestId,m.params.request.method);if(visual&&m.method==='Network.requestWillBeSent'){try{const u=new URL(m.params.request.url);if(['http:','https:'].includes(u.protocol)&&!['127.0.0.1','localhost'].includes(u.hostname))externalHosts.add(u.hostname)}catch{}}if(phase2b&&m.method==='Network.responseReceived'&&requestMethods.get(m.params.requestId)==='POST'&&m.params.response.url.endsWith('/turns'))modelReplies.push({status:m.params.response.status});if(visual&&m.method==='Runtime.exceptionThrown')runtimeExceptions.push({text:m.params.exceptionDetails.text,description:m.params.exceptionDetails.exception?.description?.slice(0,1000)||"",url:m.params.exceptionDetails.url||""});if(m.id){const p=waiting.get(m.id);if(!p)return;waiting.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++serial;waiting.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}))});
 return {send,ws};
}
if(visual&&process.env.IS_BROWSER_APPEND!=="1")report={kind:'actual_chrome_webgl_visual_replay',new_live_qloo_requests:0,new_openai_requests:0,journeys:[],safari:{status:'NOT_RUN',reason:'No new Safari execution in this visual pass'}};
const {send,ws}=await connect();
const chosen=process.argv[2];const desiredEnding=process.env.IS_BROWSER_ENDING||'together';
try{
 for(const [category,name] of seeds.filter(([c])=>!chosen||chosen.split(',').includes(c))){
  report.journeys=report.journeys.filter(j=>j.category!==category);
  const entry={category,seed:name,status:'FAIL',checks:[]};report.journeys.push(entry);
  const context=playerPresentation?await send('Target.createBrowserContext'):{};
  const {targetId}=await send('Target.createTarget',{url:'about:blank',...context});
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
  async function ask(text,change=false,failure=false,double=false){
   const before=await until(async()=>{const v=await view();return v&&!v.blocked&&!v.busy&&!v.pending?v:null},"composer ready");const count=modelReplies.length;
   await evaluate(`(()=>{document.querySelector('#agent-text').value=${JSON.stringify(text)};document.querySelector('#agent-form').requestSubmit();${double?"document.querySelector('#agent-form').requestSubmit();":""}})()`);
   await until(()=>modelReplies.length>count,'bounded local-model response',70000);await until(async()=>!(await view()).busy,'local turn settled',10000);const after=await idle();
   if(modelReplies.length!==count+1)throw Error('Duplicate model HTTP submission');
   if(modelReplies.at(-1).status!==(failure?503:200))throw Error('Unexpected local model response '+modelReplies.at(-1).status);
   if(change ? after.revision<=before.revision : after.revision!==before.revision)throw Error('Model turn violated expected revision boundary');
   if(!failure){const a=await(await fetch(backend+'/verification/local-ai/adapter')).json();modelReplies.at(-1).inference_requests=a.latest_turn_inference_requests;}
   entry.checks.push(failure?'controlled model outage preserves revision':'actual local model '+(change?'proposes engine-validated quest change':'returns read-only dialogue/evidence')+(double?'; duplicate submit rejected':''));
   return after;
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
   if(phase2b||playerPresentation)await cdp('Emulation.setDeviceMetricsOverride',{width:playerPresentation?1600:1280,height:900,deviceScaleFactor:1,mobile:false});
   await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Network.enable');await cdp('Network.setCacheDisabled',{cacheDisabled:true});
   await cdp('Page.navigate',{url:web});
   await until(()=>evaluate('typeof player!=="undefined" && !!player && !!current && current.cultural_available'),'Unity ready',90000);
   await sleep(700);await screenshot('opening');
   if(phase2b&&!playerPresentation)await evaluate(`document.querySelector('#access-toggle').click()`);
   const label=await evaluate('document.querySelector("#status").textContent');if(!label.includes('LOCAL CAPTURE REPLAY'))throw Error('Missing replay attribution');
   await evaluate(`(()=>{document.querySelector('#culture-seed').value=${JSON.stringify(name)};document.querySelector('#culture-category').value=${JSON.stringify(category)};document.querySelector('#culture-form').requestSubmit();})()`);
   await click('cultural');
   await until(async()=>{const v=await view();return v&&(!v.title||v.actions.some(a=>a.command.startsWith('confirm:')))},'resolution');
   let expectedSeedName=name;
   let v=await view();if(v.title){const a=v.actions.find(a=>a.label.includes('The Lego Group'));if(!a)throw Error('Expected canonical brand missing');expectedSeedName=a.label.slice('Confirm: '.length).split(' · ')[0];await click(a.command);entry.checks.push('confirmed actual returned canonical brand')}
   await until(async()=>{const v=await view();return v&&!v.title&&!v.busy},'created world');
   if(investigation){await screenshot('tutorial');await cdp('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,x:1600*.215,y:900*.315});await sleep(100);await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,x:1600*.215,y:900*.315});await sleep(200);}
   v=await idle();if(!v.objectives.some(t=>t.includes('cultural memory')))throw Error('Cultural quest absent');entry.checks.push('cultural context creates required objective');
   if(phase2b){const result=await ask('Show the saved cultural seed and recommendation names without changing progress.',false,false,true);if(!result.story.startsWith('Saved Qloo evidence (server-rendered):'))throw Error('Factual tool attribution missing');}
   if(visual){
    await screenshot('record-bar');if(playerPresentation&&await evaluate('getComputedStyle(document.querySelector("#accessible-controls")).display')!=='none')throw Error('Alternative controls intrude on normal composition');
    await click('scanner');await until(async()=>(await view()).panel==='scanner','Scanner actual UI');if(investigation){await evaluate("player.SendMessage('Infinite Stories','OnBrowserCommand','scan:inspect')");await until(async()=>(await view()).panel_text?.includes('SEED · '),'saved evidence inspection');}await screenshot('scanner');if(phase2b){await cdp('Emulation.setDeviceMetricsOverride',{width:800,height:900,deviceScaleFactor:1,mobile:false});await evaluate('window.dispatchEvent(new Event("resize"))');await screenshot('scanner-narrow');if(await evaluate('document.documentElement.scrollWidth>innerWidth+1'))throw Error('Narrow layout horizontal overflow');await cdp('Emulation.setDeviceMetricsOverride',{width:playerPresentation?1600:1280,height:900,deviceScaleFactor:1,mobile:false});}
    if(!(await view()).panel_text?.includes('SEED · '+expectedSeedName+' ['+category+']'))throw Error('Scanner lost actual saved seed');
    const revision=(await view()).revision;await click('compare');await until(async()=>(await view()).panel_text?.includes('AUTHORED CONTROL'),'honest authored comparison');await screenshot('authored-control');if((await view()).revision!==revision)throw Error('Read-only comparison mutated state');
    await click('continue');await click('journal');await until(async()=>(await view()).panel==='journal','Journal actual UI');await screenshot('journal');if(!(await view()).panel_text?.includes('CONFIRMED OBJECTIVES'))throw Error('Journal missing confirmed objectives');await click('continue');
    entry.checks.push('actual Scanner, authored-control comparison and confirmed Journal open; comparison preserves revision');
   }
   // Unsupported browser command must not bypass client or authoritative progression.
   const before=v.revision;await evaluate(`player.SendMessage('Infinite Stories','OnBrowserCommand','choose:cultural_echo_0:fabricated')`);await sleep(250);
   if((await view()).revision!==before)throw Error('Fabricated answer changed progress');entry.checks.push('unsupported browser answer leaves revision unchanged');
   for(let stage=0;stage<4;stage++){
    if(investigation&&stage===1){await move(12,6);const prior=await idle();const bad=prior.actions.find(a=>a.command.includes('hypothesis_screen_0'));if(!bad)throw Error('Unsupported screening claim not offered');await click(bad.command);await sleep(500);if((await idle()).revision!==prior.revision)throw Error('Unsupported screening claim mutated state');await choose('choose:screening_note_0:trace_');entry.checks.push('screening evidence traced; unsupported collaboration rejected without mutation');}
    if(stage===2){await move(12,6);await choose('choose:cultural_echo_0:');entry.checks.push('actual cultural card completed through controller and server rules')}
    await move(13,9);
    if(visual){if(playerPresentation)await screenshot(['record-bar-interior','cinema-interior','boutique-interior','gate-interior'][stage]);await click('interact');await until(async()=>(await view()).panel==='dialogue','dialogue UI');await screenshot(['record-bar-dialogue','cinema-dialogue','boutique-dialogue','gate-dialogue'][stage]);await click('continue');}
    if(investigation&&stage===3){const prior=await idle();await click('choose:beacon:hypothesis_curator');await sleep(500);if((await idle()).revision!==prior.revision)throw Error('Unsupported personality claim mutated state');await choose('choose:beacon:prove_');entry.checks.push('Curator validates actual saved affinity and rejects personality claim');}
    if(phase2b&&stage===0){
     await ask("I accept Mara's hand-drawn map.",true);
     const fault=process.env.IS_BROWSER_MODEL_FAULT_FILE||root+'reports/local/phase2b/backend/model-scenario';await fs.writeFile(fault,'unavailable');try{await ask('Describe the listening room without changing progress.',false,true);}finally{await fs.writeFile(fault,'');}
     await cdp('Page.reload',{ignoreCache:true});await until(()=>evaluate('!!player&&!!current&&current.title'),'refresh after outage',90000);await click('resume');await until(async()=>!(await view()).title,'resume after outage');await ask('Describe the listening room without changing progress.',false);await click('story');await screenshot('actual-local-story');await click('continue');
    }else await choose(['choose:mara:take_map','choose:ivo:learn_rhythm','choose:sera:promise_guard',desiredEnding==='keeper'?'choose:beacon:leave_keeper':'choose:beacon:light_together'][stage]);
    if(stage<3){await move(29,8);await choose('travel:');await until(async()=>{const v=await view();return v.visits===stage+2&&!v.busy},'area transition')}
    console.log(JSON.stringify({category,milestone:'stage '+(stage+1)}));
   }
   v=await idle();if(v.ending!==desiredEnding||v.visits!==4||!v.objectives.every(t=>t.startsWith('Complete:')))throw Error('Invalid ending/objectives');
   entry.checks.push('four-area quest and ending completed');const rev=v.revision;const goals=v.objectives;
   await screenshot('taste-card');
   await cdp('Page.captureScreenshot',{format:'png'}).then(async r=>{await fs.mkdir((visual || root+'reports/local/browser-acceptance'),{recursive:true});await fs.writeFile((visual || root+'reports/local/browser-acceptance')+'/chrome-'+category+'.png',Buffer.from(r.data,'base64'))});
   await cdp('Page.reload',{ignoreCache:true});
   await until(()=>evaluate('typeof player!=="undefined" && !!player && !!current'),'reloaded Unity',90000);
   await click('resume');await until(async()=>{const v=await view();return v&&!v.title&&v.ending===desiredEnding},'resume ending');
   const resumed=await idle();if(resumed.revision!==rev||JSON.stringify(resumed.objectives)!==JSON.stringify(goals))throw Error('Resume changed progress');
   if(phase2b){entry.local_model_turn_responses=modelReplies; if(modelReplies.length!==4)throw Error('Local-model request ceiling changed');}
   entry.checks.push('page refresh/resume preserves exact revision and completed objectives without duplication');entry.ending=resumed.ending;entry.visits=resumed.visits;entry.revision=resumed.revision;entry.status='PASS';
  }catch(error){entry.error=error.message;entry.last_public_view=await view().catch(()=>null)}
  if(visual){report.non_loopback_browser_hosts=[...externalHosts];report.browser_runtime_exceptions=runtimeExceptions;}
  await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({category,status:entry.status,error:entry.error}));
  await send('Target.closeTarget',{targetId});if(context.browserContextId)await send('Target.disposeBrowserContext',{browserContextId:context.browserContextId});
 }
}finally{ws.close(); if(report.journeys.some(j=>j.status!=='PASS'))process.exitCode=1;}
