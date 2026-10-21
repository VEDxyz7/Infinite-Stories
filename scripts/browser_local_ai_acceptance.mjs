// Actual headless Chrome/WebGL -> local Ollama; historical Qloo replay only. No hosted inference.
// Requires isolated Chrome on9223 and explicitly labelled loopback replay on8043.
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const replayCapabilities=await(await fetch('http://127.0.0.1:8044/v1/capabilities')).json();
if(replayCapabilities.game_master_inference_mode!=='local_loopback')throw Error('Actual local model backend required');
if(replayCapabilities.verification_mode!=='captured_response_replay')throw Error('Refusing browser tests against a backend that is not explicitly captured-response replay');
const output=process.env.IS_AI_BROWSER_OUTPUT||root+'reports/local/browser-local-ai-qwen35-recovery-final.json';
try{await fs.access(output);throw Error('Evidence exists')}catch(e){if(e.code!=='ENOENT')throw e}
let modelHttpResponses=0;let failedModelHttpResponses=0;let abortNextModelReply=false,lostCommittedReplies=0,replayedReceipts=0;const turnRequestIds=new Set();const requestMethods=new Map();
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let report={kind:'actual_chrome_webgl_local_ollama_with_captured_qloo_replay',new_live_qloo_requests:0,hosted_model_requests:0,api_routing:'CDP test-only 8043 to isolated8044; Unity binaries unchanged; Resume template recovery fix applied',journeys:[]};
const seeds=[['artist','David Bowie']];
async function connect(){
 const info=await(await fetch('http://127.0.0.1:9223/json/version')).json();
 report.chrome_version=info.Browser;
 const ws=new WebSocket(info.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});
 let serial=0;const waiting=new Map();
 ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.method==='Fetch.requestPaused'){
 const p=m.params;
 if(p.responseStatusCode!==undefined){
  if(abortNextModelReply&&p.request.method==='POST'&&p.request.url.endsWith('/turns')&&p.responseStatusCode===200){abortNextModelReply=false;lostCommittedReplies++;send('Fetch.failRequest',{requestId:p.requestId,errorReason:'Aborted'},m.sessionId).catch(()=>{});}
  else send('Fetch.continueRequest',{requestId:p.requestId},m.sessionId).catch(()=>{});
 }else send('Fetch.continueRequest',{requestId:p.requestId,url:p.request.url.replace('127.0.0.1:8043','127.0.0.1:8044')},m.sessionId).catch(()=>{});
}
if(m.method==='Network.requestWillBeSent'&&m.params.request.method==='POST'&&m.params.request.url.endsWith('/turns'))turnRequestIds.add(m.params.requestId);
if(m.method==='Network.loadingFinished'&&turnRequestIds.has(m.params.requestId))send('Network.getResponseBody',{requestId:m.params.requestId},m.sessionId).then(r=>{const b=JSON.parse(r.base64Encoded?Buffer.from(r.body,'base64').toString():r.body);if(b.idempotent_replay)replayedReceipts++;}).catch(()=>{});
if(m.method==='Network.requestWillBeSent')requestMethods.set(m.params.requestId,m.params.request.method);if(m.method==='Network.responseReceived'&&requestMethods.get(m.params.requestId)==='POST'&&m.params.response.url.endsWith('/turns')){if(m.params.response.status===200)modelHttpResponses++;else if(m.params.response.status>=400)failedModelHttpResponses++;}if(m.id){const p=waiting.get(m.id);if(!p)return;waiting.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++serial;waiting.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}))});
 return {send,ws};
}
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
  async function ask(text,change=true,expectFailure=false){
   const before=await idle();const received=modelHttpResponses;const failuresBefore=failedModelHttpResponses;const lostBefore=lostCommittedReplies;const replayBefore=replayedReceipts;
   const r=await evaluate("(()=>{const r=document.querySelector('#unity-canvas').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()");
   async function mouse(x,y){await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});await sleep(100);await cdp('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await sleep(100);await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});await sleep(100);}
   await mouse(r.x+r.w*.3,r.y+r.h*.955);
   await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:4});
   await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:4});
   await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
   await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
   for(const ch of text){await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:ch,text:ch,unmodifiedText:ch,windowsVirtualKeyCode:ch.toUpperCase().charCodeAt(0)});await sleep(25);await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:ch,windowsVirtualKeyCode:ch.toUpperCase().charCodeAt(0)});}
   await mouse(r.x+r.w*.84,r.y+r.h*.955);
   if(expectFailure==='unavailable'){
    await until(()=>failedModelHttpResponses>failuresBefore,'controlled outage response',15000);
    const failed=await until(async()=>{const v=await view();return v&&!v.busy?v:null},'confirmed failure');
    if(failed.revision!==before.revision||failed.pending)throw Error('Confirmed outage corrupted state or left a terminal pending request');
    await cdp('Page.reload',{ignoreCache:true});await until(()=>evaluate('!!player&&!!current&&current.title'),'title after outage refresh',90000);await click('resume');
    const recovered=await until(async()=>{const v=await view();return v&&!v.title&&!v.busy&&!v.pending?v:null},'Resume after outage');
    if(recovered.revision!==before.revision)throw Error('Resume duplicated progress');
    entry.checks.push('controlled provider outage preserves confirmed progress and clears terminal request; refresh/resume restores exact save');
    return recovered;
   }
   if(expectFailure==='lost'){
    await until(()=>lostCommittedReplies>lostBefore,'server-completed response abort',100000);
    const failed=await until(async()=>{const v=await view();return v&&!v.busy&&v.pending?v:null},'uncertain response pending');
    if(failed.revision!==before.revision)throw Error('Lost response changed visible state');
    await click('resume');await until(()=>replayedReceipts>replayBefore,'same-ID receipt replay',20000);
    const recovered=await idle();if(recovered.revision!==before.revision)throw Error('Receipt recovery duplicated progress');
    entry.checks.push('aborted response after server commit: pending Resume enabled; same-ID receipt replay, no duplicate progression');
    return recovered;
   }
   await until(()=>modelHttpResponses>received,'actual model response',100000);
   const after=await idle();
   if(change&&after.revision<=before.revision)throw Error('Model did not apply expected quest choice');
   if(!change&&after.revision!==before.revision)throw Error('Dialogue unexpectedly progressed quest');
   console.log(JSON.stringify({model_turn:modelHttpResponses,revision:after.revision}));
  }
  async function choose(prefix){
   const v=await idle();const a=v.actions.find(a=>a.command.startsWith(prefix));
   if(!a)throw Error('Expected nearby allowed choice missing: '+prefix);
   await click(a.command);await until(async()=>{const n=await view();return n&&n.revision>v.revision&&!n.busy},'choice confirmation');
  }
  try{
   await cdp('Page.enable');await cdp('Page.bringToFront');await cdp('Emulation.setFocusEmulationEnabled',{enabled:true});await cdp('Runtime.enable');await cdp('Network.enable');await cdp('Network.setCacheDisabled',{cacheDisabled:true});
   await cdp('Fetch.enable',{patterns:[{urlPattern:'http://127.0.0.1:8043/*'},{urlPattern:'http://127.0.0.1:804*/*/turns',requestStage:'Response'}]});
   await cdp('Page.navigate',{url:'http://127.0.0.1:8081'});
   await until(()=>evaluate('typeof player!=="undefined" && !!player && !!current && current.cultural_available'),'Unity ready',90000);
   const label=await evaluate('document.querySelector("#status").textContent');if(!label.includes('LOCAL CAPTURE REPLAY'))throw Error('Missing replay attribution');
   await evaluate(`(()=>{document.querySelector('#culture-seed').value=${JSON.stringify(name)};document.querySelector('#culture-category').value=${JSON.stringify(category)};document.querySelector('#culture-form').requestSubmit();})()`);
   await click('cultural');
   await until(async()=>{const v=await view();return v&&(!v.title||v.actions.some(a=>a.command.startsWith('confirm:')))},'resolution');
   let v=await view();if(v.title){const a=v.actions.find(a=>a.label.includes('The Lego Group'));if(!a)throw Error('Expected canonical brand missing');await click(a.command);entry.checks.push('confirmed actual returned canonical brand')}
   await until(async()=>{const v=await view();return v&&!v.title&&!v.busy},'created world');
   v=await idle();if(!v.objectives.some(t=>t.includes('cultural memory')))throw Error('Cultural quest absent');entry.checks.push('cultural context creates required objective');
   // Unsupported browser command must not bypass client or authoritative progression.
   const before=v.revision;await evaluate(`player.SendMessage('Infinite Stories','OnBrowserCommand','choose:cultural_echo_0:fabricated')`);await sleep(250);
   if((await view()).revision!==before)throw Error('Fabricated answer changed progress');entry.checks.push('unsupported browser answer leaves revision unchanged');
   for(let stage=0;stage<4;stage++){
    if(stage===2){await move(12,6);const card=(await idle()).actions.find(a=>a.command.startsWith('choose:cultural_echo_0:'));await ask('I choose to carry this memory card. '+card.label);entry.checks.push('actual local model chose cultural card through Unity text input and server rules')}
    await move(14,9);
    if(stage===0){await ask('Show me the saved cultural evidence: the seed and recommendation names, and what the aggregate affinity does and does not establish about collaboration or my personality. Keep quest progress unchanged.',false);if(!(await view()).story.startsWith('Saved Qloo evidence (server-rendered):'))throw Error('Missing authoritative evidence attribution');entry.checks.push('actual local model selects read-only evidence tool; source clearly server-rendered; revision unchanged');}
    await ask(["I accept Mara's hand-drawn map.","I tell Ivo my map's story in exchange for his rhythm.","I promise Sera to protect the private letters.","I light the beacon and leave together with my friends."][stage]);
    if(stage===0){const fault=process.env.IS_AI_BROWSER_FAULT_FILE||root+'reports/local/local-ai-browser/model-scenario';await fs.writeFile(fault,'unavailable');try{await ask('Describe the copper lamps without changing anything.',false,'unavailable');}finally{await fs.writeFile(fault,'');}await ask('Describe the copper lamps without changing anything.',false);entry.checks.push('real local inference recovers on a new turn after controlled outage');abortNextModelReply=true;await ask('Describe the harbor without changing anything.',false,'lost');}
    if(stage<3){await move(29,8);await choose('travel:');await until(async()=>{const v=await view();return v.visits===stage+2&&!v.busy},'area transition')}
    console.log(JSON.stringify({category,milestone:'stage '+(stage+1)}));
   }
   v=await idle();if(v.ending!=='together'||v.visits!==4||!v.objectives.every(t=>t.startsWith('Complete:')))throw Error('Invalid ending/objectives');
   entry.checks.push('four-area quest and ending completed');const rev=v.revision;const goals=v.objectives;
   await cdp('Page.captureScreenshot',{format:'png'}).then(async r=>{await fs.mkdir(root+'reports/local/browser-acceptance',{recursive:true});await fs.writeFile(root+'reports/local/browser-acceptance/local-ai-chrome-'+category+'.png',Buffer.from(r.data,'base64'))});
   await cdp('Page.reload',{ignoreCache:true});
   await until(()=>evaluate('typeof player!=="undefined" && !!player && !!current'),'reloaded Unity',90000);
   await click('resume');await until(async()=>{const v=await view();return v&&!v.title&&v.ending==='together'},'resume ending');
   const resumed=await idle();if(resumed.revision!==rev||JSON.stringify(resumed.objectives)!==JSON.stringify(goals))throw Error('Resume changed progress');
   entry.checks.push('page refresh/resume preserves exact revision and completed objectives without duplication');entry.browser_successful_turn_responses=modelHttpResponses;entry.replayed_turn_receipts=replayedReceipts;entry.simulated_lost_committed_responses=lostCommittedReplies;entry.controlled_provider_outages=failedModelHttpResponses;entry.ending=resumed.ending;entry.visits=resumed.visits;entry.revision=resumed.revision;entry.status='PASS';
  }catch(error){entry.error=error.message;entry.last_public_view=await view().catch(()=>null)}
  await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({category,status:entry.status,error:entry.error}));
  await send('Target.closeTarget',{targetId});
 }
}finally{ws.close(); if(report.journeys.some(j=>j.status!=='PASS'))process.exitCode=1;}
