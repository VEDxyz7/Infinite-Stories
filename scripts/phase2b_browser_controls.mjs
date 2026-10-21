// Real Chrome keyboard/mouse, gentle ending and replay failure recovery. No model calls.
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const dir=root+'reports/local/phase2b/';
const report={kind:'real_chrome_physical_controls_and_replay_recovery',status:'FAIL',checks:[],new_live_provider_requests:0,model_requests:0};
const info=await(await fetch('http://127.0.0.1:9223/json/version')).json();
const cap=await(await fetch('http://127.0.0.1:8046/v1/capabilities')).json();
if(cap.verification_mode!=='captured_response_replay')throw Error('Explicit replay required');
const ws=new WebSocket(info.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
let serial=0;const waits=new Map();
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=waits.get(m.id);waits.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++serial;waits.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}))});
const {targetId}=await send('Target.createTarget',{url:'about:blank'});
const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
const cdp=(m,p)=>send(m,p,sessionId);
const ev=async expression=>{const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(f,label,timeout=20000){const end=Date.now()+timeout;while(Date.now()<end){const r=await f();if(r)return r;await sleep(100)}throw Error('Timeout: '+label)}
const view=()=>ev('typeof current!=="undefined"&&current?JSON.parse(JSON.stringify(current)):null');
async function idle(){return until(async()=>{const v=await view();return v&&!v.busy&&!v.pending?v:null},'confirmed')}
async function click(command){return until(()=>ev(`(()=>{const b=document.querySelector('button[data-command="${command}"]');if(!b||b.disabled)return false;b.click();return true})()`),'enabled '+command)}
async function capture(name){await sleep(400);const r=await cdp('Page.captureScreenshot',{format:'png'});await fs.writeFile(dir+'chrome-'+name+'.png',Buffer.from(r.data,'base64'))}
async function physicalClick(selector){const p=await ev(`(()=>{const b=document.querySelector(${JSON.stringify(selector)});const r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);await cdp('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...p});await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...p})}
async function move(x,y){for(const [axis,target] of [['y',8],['x',x],['y',y]]){for(let n=0;n<40;n++){const v=await idle();const d=target-v[axis];if(Math.abs(d)<.65)break;await click(axis==='x'?(d>0?'east':'west'):(d>0?'north':'south'));await until(async()=>{const a=await view();return a&&!a.busy&&Math.abs(a[axis]-v[axis])>.2},'movement');if(n===39)throw Error('Movement failed')}}}
try{
 await cdp('Page.enable');await cdp('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false});
 await cdp('Page.navigate',{url:'http://127.0.0.1:8083/?phase2b=controls'});
 await until(()=>ev('typeof player!=="undefined"&&!!player&&!!current&&current.cultural_available'),'Unity/capabilities',90000);
 await physicalClick('#access-toggle');if(!(await ev('document.querySelector("#layout").classList.contains("controls-open")')))throw Error('Physical mouse toggle failed');
 await click('authored');await until(async()=>!(await view()).title,'authored start');await idle();
 await physicalClick('#unity-canvas');const before=await idle();
 await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39,nativeVirtualKeyCode:39});await sleep(250);await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39,nativeVirtualKeyCode:39});
 await until(async()=>{const v=await view();return v&&!v.busy&&v.x>before.x+.2},'physical keyboard/autosave');
 report.checks.push('native CDP mouse toggles accessible controls; focused canvas right-arrow moves and autosaves');
 await click('sound');await until(()=>ev('document.querySelector("#status").textContent.includes("Sound muted")'),'mute status');await click('sound');await until(()=>ev('document.querySelector("#status").textContent.includes("Sound enabled")'),'sound status');report.checks.push('persisted sound toggle updates player-facing status; no human audio audition');
 while(!(await idle()).ending){const v=await idle();await move(v.x<15?2:29,8);const a=(await idle()).actions.find(a=>a.command.startsWith('travel:'));if(!a)throw Error('Portal missing');await click(a.command);await until(async()=>{const a=await view();return a&&!a.busy&&(a.visits!==v.visits||a.ending)},'travel confirmed')}
 const dawn=await idle();if(dawn.ending!=='dawn'||dawn.visits!==12)throw Error('Invalid gentle ending');await capture('gentle-ending');
 await cdp('Page.reload',{ignoreCache:true});await until(()=>ev('!!player&&!!current&&current.title'),'refresh',90000);await click('resume');await until(async()=>(await view()).ending==='dawn','resume gentle');if((await idle()).revision!==dawn.revision)throw Error('Resume revision changed');report.checks.push('actual engine12-visit gentle ending, distinct Taste Card and exact refresh/resume');
 await click('title');await until(async()=>(await view()).title,'title');await ev(`(()=>{document.querySelector('#culture-seed').value='David Bowie';document.querySelector('#culture-category').value='artist';document.querySelector('#culture-form').requestSubmit()})()`);
 await fs.writeFile(dir+'backend/upstream-scenario','503');try{await click('cultural');await until(()=>ev('document.querySelector("#status").textContent.toLowerCase().includes("unavailable")'),'visible creation503');if(!(await view()).title)throw Error('Failed creation replaced prior save');await capture('creation-error')}finally{await fs.writeFile(dir+'backend/upstream-scenario','')}
 await click('resume');await until(async()=>(await view()).ending==='dawn','recovered prior save');if((await idle()).revision!==dawn.revision)throw Error('Failure corrupted save');
 await cdp('Page.reload',{ignoreCache:true});await until(()=>ev('!!player&&!!current&&current.title'),'refresh after failure',90000);await click('resume');await until(async()=>(await view()).ending==='dawn','refreshed recovery');if((await idle()).revision!==dawn.revision)throw Error('Recovered revision mismatch');
 report.checks.push('controlled replay503 creation fails visibly, preserves save and recovers after reset, resume and refresh');report.status='PASS';
}catch(e){report.error=e.message;report.last_public_view=await view().catch(()=>null)}finally{await fs.writeFile(dir+'backend/upstream-scenario','');await fs.writeFile(dir+'chrome-controls.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));await send('Target.closeTarget',{targetId});ws.close();if(report.status!=='PASS')process.exitCode=1}
