// Observe the unmodified official CLI; allow one exact-host GET, no redirects/retries.
import fs from 'node:fs';
import { createHash } from 'node:crypto';
const realFetch = globalThis.fetch;
let attempts = 0;
const output = process.env.IS_QLOO_EVIDENCE;
const expectedPath = process.env.IS_QLOO_PATH;
function save(record) { fs.writeFileSync(output, JSON.stringify(record, null, 2), {mode:0o600}); }
function projection(e) {
  if (!e || typeof e !== 'object') return {};
  const out = {observed_fields: Object.keys(e)};
  for (const k of ['entity_id','name','type','subtype','types','disambiguation','popularity']) if (k in e) out[k]=e[k];
  if (e.properties && typeof e.properties === 'object') {
    out.property_fields=Object.keys(e.properties); out.properties={};
    for (const k of ['release_year','description','short_description','content_rating','duration']) if (k in e.properties) out.properties[k]=e.properties[k];
  }
  if (Array.isArray(e.tags)) {out.tag_count=e.tags.length; out.tags=e.tags.slice(0,30).map(t=>({...Object.fromEntries(['id','tag_id','name','type'].filter(k=>k in t).map(k=>[k,t[k]])),observed_fields:Object.keys(t)}));}
  if (e.query && typeof e.query==='object') out.query_fields=Object.keys(e.query);
  return out;
}
globalThis.fetch = async (input, options={}) => {
  const u=new URL(typeof input==='string' || input instanceof URL ? input : input.url);
  if (++attempts !== 1 || u.origin !== 'https://hackathon.api.qloo.com' || u.pathname !== expectedPath || options.method !== 'GET') throw Error('BOUNDED_REQUEST_REJECTED');
  const record={at_utc:new Date().toISOString(),method:'GET',origin:u.origin,path:u.pathname,params:Object.fromEntries(u.searchParams),fetch_attempts:attempts,http_status:null};
  save(record);
  const start=performance.now();
  try {
    const response=await realFetch(input,{...options,redirect:'error',signal:AbortSignal.timeout(25000)});
    record.http_status=response.status; record.headers_elapsed_ms=Math.round(performance.now()-start);
    const bytes=await response.clone().arrayBuffer();
    record.total_elapsed_ms=Math.round(performance.now()-start);
    record.body_sha256=createHash('sha256').update(new Uint8Array(bytes)).digest('hex');
    const body=JSON.parse(Buffer.from(bytes).toString('utf8'));
    record.top_level_fields=Object.keys(body); record.upstream_success=body.success ?? null;
    let entities=null;
    if (Array.isArray(body.results)) {entities=body.results; record.container='results[]';}
    else if (Array.isArray(body.results?.entities)) {entities=body.results.entities; record.container='results.entities[]';}
    record.result_count=entities?.length ?? null;
    record.entities=entities ? entities.map(projection) : [];
    record.outcome=response.ok ? (entities===null ? 'SCHEMA_UNKNOWN' : entities.length ? 'DATA_RETURNED' : 'EMPTY') : 'HTTP_ERROR';
    // Never persist upstream error text, headers, or the full response body.
    save(record); return response;
  } catch (error) {
    record.total_elapsed_ms=Math.round(performance.now()-start);
    record.outcome=record.http_status ? 'RESPONSE_DECODE_ERROR' : 'NETWORK_TLS_OR_TIMEOUT';
    save(record); throw Error(record.outcome);
  }
};
