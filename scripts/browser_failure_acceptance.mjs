// Real Chrome WebGL, controlled application HTTP errors via CDP interception.
// Separate from provider MockTransport tests. No live provider calls.
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const replayCapabilities=await(await fetch('http://127.0.0.1:8043/v1/capabilities')).json();
if(replayCapabilities.verification_mode!=='captured_response_replay')throw Error('Refusing browser tests against a backend that is not explicitly captured-response replay');
const info=await(await fetch('http://127.0.0.1:9223/json/version')).json();
const ws=new WebSocket(info.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});
const transportOnly=process.argv.includes('--transport-only');
let serial=0;const waiting=new Map();let fault=null;let intercepted=0;let lastRequestId=null;const requestIds=[];
const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++serial;waiting.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}))});
ws.onmessage=async event=>{const m=JSON.parse(event.data);if(m.id){const p=waiting.get(m.id);waiting.delete(m.id);if(p)m.error?p.reject(Error(m.error.message)):p.resolve(m.result);return}if(m.method==='Fetch.requestPaused'){
 const r=m.params;const matching=r.request.method==='POST'&&new URL(r.request.url).pathname==='/v1/sessions';
 if(matching){lastRequestId=JSON.parse(r.request.postData).request_id;requestIds.push(lastRequestId)}
 if(fault&&matching){intercepted++;if(fault.abort){await send('Fetch.failRequest',{requestId:r.requestId,errorReason:'ConnectionFailed'},m.sessionId);return}if(fault.malformed){await send('Fetch.fulfillRequest',{requestId:r.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'application/json'},{name:'Access-Control-Allow-Origin',value:'http://127.0.0.1:8081'}],body:Buffer.from('not valid JSON').toString('base64')},m.sessionId);return}await send('Fetch.fulfillRequest',{requestId:r.requestId,responseCode:fault.status,responseHeaders:[{name:'Content-Type',value:'application/json'},{name:'Access-Control-Allow-Origin',value:'http://127.0.0.1:8081'}],body:Buffer.from(JSON.stringify({error:{code:fault.code,message:fault.message,request_id:'local-controlled-failure'}})).toString('base64')},m.sessionId)}else await send('Fetch.continueRequest',{requestId:r.requestId},m.sessionId)
}};
const {targetId}=await send('Target.createTarget',{url:'about:blank'});const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});const cdp=(m,p={})=>send(m,p,sessionId);
const evaluate=async expression=>{const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));const view=()=>evaluate('typeof current!=="undefined"&&current?JSON.parse(JSON.stringify(current)):null');
async function until(fn,label,timeout=20000){const end=Date.now()+timeout;while(Date.now()<end){const x=await fn();if(x)return x;await sleep(100)}throw Error('Timeout: '+label)}
async function click(command){await until(()=>evaluate(`(()=>{const b=document.querySelector('button[data-command="${command}"]');if(!b||b.disabled)return false;b.click();return true})()`),'enabled '+command)}
const result={kind:'automated_chrome_webgl_controlled_application_http_failures',new_live_qloo_requests:0,new_openai_requests:0,cases:[]};
try{
 await cdp('Runtime.enable');await cdp('Page.enable');await cdp('Network.enable');await cdp('Network.setCacheDisabled',{cacheDisabled:true});await cdp('Fetch.enable',{patterns:[{urlPattern:'http://127.0.0.1:8043/v1/sessions*',requestStage:'Request'}]});
 await cdp('Page.navigate',{url:'http://127.0.0.1:8081'});await until(()=>evaluate('typeof player!=="undefined"&&!!player&&!!current'),'ready',90000);
 await click('resume');await until(async()=>{const v=await view();return v&&!v.title&&!v.busy},'saved ending');
 const original=await view();if(!transportOnly&&original.ending!=='together')throw Error('Needs prior completed journey saved by the four-path runner');
 for(const [status,code,message] of (transportOnly?[]:[[422,'QLOO_REQUEST_REJECTED','The cultural service rejected this seed or query. Choose another interest; no world was changed.'],[503,'QLOO_AUTH','The cultural service credential or category is not authorized.'],[429,'QLOO_RATE_LIMIT','The cultural service is rate limited. No world was changed.'],[503,'QLOO_UPSTREAM','The cultural service is unavailable. No world was changed.'],[503,'QLOO_NETWORK','The cultural service could not be reached. No world was changed.'],[503,'QLOO_TIMEOUT','The cultural service timed out. No world was changed.'],[503,'QLOO_RESPONSE_INVALID','The cultural service returned unsupported data. No world was changed.'],[422,'QLOO_EMPTY','No cultural results are available for that seed. Choose another interest.'],[422,'QLOO_UNRESOLVED','No cultural entity matched. Check the name and category.']])){
  const item={code,status:'FAIL'};result.cases.push(item);
  try{
   await click('title');await until(async()=>{const v=await view();return v&&v.title},'title');
   await evaluate(`(()=>{document.querySelector('#culture-seed').value='David Bowie';document.querySelector('#culture-category').value='artist';document.querySelector('#culture-form').requestSubmit()})()`);
   fault={status,code,message};const count=intercepted;await click('cultural');
   await until(()=>evaluate(`document.querySelector('#status').textContent.includes(${JSON.stringify(message)})`),'safe error surfaced');
   await sleep(500);let v=await view();if(v.pending||v.busy||intercepted!==count+1)throw Error('Error retained pending write or auto-retried');
   fault=null;
   await cdp('Page.reload',{ignoreCache:true});await until(()=>evaluate('typeof player!=="undefined"&&!!player&&!!current'),'reload',90000);
   await click('resume');await until(async()=>{const v=await view();return v&&!v.title&&!v.busy},'recovered save');v=await view();
   if(v.ending!==original.ending||v.revision!==original.revision||JSON.stringify(v.objectives)!==JSON.stringify(original.objectives))throw Error('Failed creation corrupted saved quest');
   item.status='PASS';item.checks=['safe error shown with replay label','one intercepted application request; no automatic retry','no pending failed creation','browser refresh and resume preserve exact completed quest revision'];
  }catch(e){item.error=e.message;fault=null}
  console.log(JSON.stringify(item));
 }
 // Once the controlled outage is removed, a deliberate new ID can create a world.
 await click('title');await until(async()=>{const v=await view();return v&&v.title},'recovery title');
 await evaluate(`(()=>{document.querySelector('#culture-seed').value='David Bowie';document.querySelector('#culture-category').value='artist';document.querySelector('#culture-form').requestSubmit()})()`);
 await click('cultural');await until(async()=>{const v=await view();return v&&!v.title&&!v.busy},'new creation after recovery');
 const recovered=await view();result.recovery={status:recovered.revision===0&&recovered.objectives.some(t=>t.includes('David Bowie'))?'PASS':'FAIL',new_deliberate_request_id:new Set(requestIds).size===requestIds.length};

 if(transportOnly)for(const kind of ['connection_failure','malformed_application_response']){
  const item={code:kind,status:'FAIL'};result.cases.push(item);
  try{
   await cdp('Page.reload',{ignoreCache:true});await until(()=>evaluate('typeof player!=="undefined"&&!!player&&!!current'),'transport reload',90000);
   await click('resume');await until(async()=>{const v=await view();return v&&!v.title&&!v.busy},'load prior');
   await click('title');await until(async()=>{const v=await view();return v&&v.title},'transport title');
   await evaluate(`(()=>{document.querySelector('#culture-seed').value='David Bowie';document.querySelector('#culture-category').value='artist';document.querySelector('#culture-form').requestSubmit()})()`);
   fault=kind==='connection_failure'?{abort:true}:{malformed:true};const count=intercepted;
   await click('cultural');await until(async()=>{const v=await view();return v&&v.pending&&!v.busy},'uncertain response retained');
   const failedId=lastRequestId;await sleep(500);if(intercepted!==count+1)throw Error('Automatic retry observed');
   fault=null;await cdp('Page.reload',{ignoreCache:true});await until(()=>evaluate('typeof player!=="undefined"&&!!player&&!!current'),'uncertain refresh',90000);
   await click('resume');await until(async()=>{const v=await view();return v&&!v.title&&!v.busy&&!v.pending},'same ID recovery');
   if(lastRequestId!==failedId)throw Error('Recovery changed request ID');
   const v=await view();if(v.revision!==0||v.objectives.filter(t=>t.includes('cultural memory')).length!==1)throw Error('Duplicate or invalid cultural quest');
   const requests=requestIds.length;await click('retry');await sleep(200);if(requestIds.length!==requests)throw Error('Retry after confirmation repeated a creation');
   item.status='PASS';item.checks=['uncertain creation retained across browser refresh','same request ID used for explicit recovery','no automatic retry','one cultural objective, revision zero','retry after confirmation makes no application request'];
  }catch(e){item.error=e.message;fault=null}
  console.log(JSON.stringify(item));
 }
 result.original_progress={ending:original.ending,revision:original.revision,visits:original.visits};
}catch(e){result.error=e.message;result.last_public_view=await view().catch(()=>null);result.safe_status=await evaluate('document.querySelector("#status").textContent').catch(()=>null);result.controls=await evaluate('Array.from(document.querySelectorAll("button[data-command]"),b=>({command:b.dataset.command,disabled:b.disabled}))').catch(()=>null)}finally{await fs.writeFile(root+(transportOnly?'reports/BROWSER_TRANSPORT_RECOVERY_20261020.json':'reports/BROWSER_FAILURE_ACCEPTANCE_20261020.json'),JSON.stringify(result,null,2)+'\n');await send('Target.closeTarget',{targetId});ws.close();if(result.error||result.cases.some(c=>c.status!=='PASS')||result.recovery?.status!=='PASS')process.exitCode=1;}
