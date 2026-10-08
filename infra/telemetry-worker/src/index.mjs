// Locdex telemetry: anonymous, schema-validated events only.
// No client ID, IP address, request headers, prompts, code, or paths are persisted.
const STRINGS = ["event","router_version","task_class","language","repo_size_bucket","requested_change","complexity_bucket","tool_intensity_bucket","model_id","backend","os","ram_bucket","accelerator_class","selected_model","selection_reason_code","route","router_mode"];
const NULLABLE_STRINGS = ["quant","prediction_gap_bucket","fallback_model"];
const BOOLEANS = ["has_tests","has_stacktrace","escalated","user_reverted"];
const NULLABLE_BOOLEANS = ["compile_passed","tests_passed","lint_passed","validator_passed"];
const INTEGERS = ["estimated_files","dependency_fanout","context_tokens","tool_calls","edit_attempts"];
const NULLABLE_INTEGERS = ["input_tokens","output_tokens"];
const NULLABLE_NUMBERS = ["latency_ms","predicted_success_selected","cost_usd"];
const ALL = new Set([...STRINGS,...NULLABLE_STRINGS,...BOOLEANS,...NULLABLE_BOOLEANS,...INTEGERS,...NULLABLE_INTEGERS,...NULLABLE_NUMBERS]);
const ENUMS = {
 event:["routing_outcome"],
 task_class:["architecture","debugging","testing","refactor","bug_fix","repo_navigation","code_explanation","tool_heavy","code_generation","small_edit","other"],
 language:["python","typescript_javascript","go","rust","unknown"],
 repo_size_bucket:["small","medium","large"],
 requested_change:["multi_file","single_file_or_unknown"],
 complexity_bucket:["low","medium","high"],
 tool_intensity_bucket:["low","medium","high"],
 backend:["local","cloud"],
 os:["windows","linux","darwin","unknown"],
 ram_bucket:["unknown","lt12","16gb_class","24gb_class","32gb_class","64gb_plus"],
 prediction_gap_bucket:["tight","close","clear"],
 route:["local","cloud"],
 router_mode:["local_only","balanced","fast","quality"],
};
const TOKEN=/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}$/;
const REASON=/^[a-z][a-z0-9_]{0,63}$/;
function json(payload,status=200) {
 return new Response(JSON.stringify(payload),{
  status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store","x-content-type-options":"nosniff"}
 });
}
export function validateEvent(event) {
 if(event===null||typeof event!=="object"||Array.isArray(event))return false;
 const keys=Object.keys(event);
 if(keys.length!==ALL.size||keys.some(k=>!ALL.has(k)))return false;
 for(const field of [...STRINGS,...NULLABLE_STRINGS]){
  const value=event[field];
  if(NULLABLE_STRINGS.includes(field)&&value===null)continue;
  if(typeof value!=="string")return false;
  if(Object.hasOwn(ENUMS,field)){if(!ENUMS[field].includes(value))return false;}
  else if(field==="selection_reason_code"){if(!REASON.test(value))return false;}
  else if(!TOKEN.test(value)||value.includes("://")||value.includes("..")||/^[A-Za-z]:\//.test(value))return false;
 }
 for(const field of [...BOOLEANS,...NULLABLE_BOOLEANS]){
  const value=event[field];
  if(NULLABLE_BOOLEANS.includes(field)&&value===null)continue;
  if(typeof value!=="boolean")return false;
 }
 for(const field of [...INTEGERS,...NULLABLE_INTEGERS]){
  const value=event[field];
  if(NULLABLE_INTEGERS.includes(field)&&value===null)continue;
  if(!Number.isSafeInteger(value)||value<0||value>10000000)return false;
 }
 for(const field of NULLABLE_NUMBERS){
  const value=event[field];
  if(value===null)continue;
  if(typeof value!=="number"||!Number.isFinite(value)||value<0||value>10000000)return false;
  if(field==="predicted_success_selected"&&value>1)return false;
 }
 return true;
}
export function validateBatch(data){
 if(data===null||typeof data!=="object"||Array.isArray(data))return false;
 if(Object.keys(data).sort().join(",")!=="events,schema_version"||data.schema_version!==1)return false;
 if(!Array.isArray(data.events)||data.events.length<1||data.events.length>25)return false;
 return data.events.every(validateEvent);
}
function projectMetric(binding,event){
 // Position is part of the analytics SQL query contract; keep stable.
 binding.writeDataPoint({
  blobs:[event.event,event.task_class,event.language,event.repo_size_bucket,event.requested_change,event.model_id,event.backend,event.os,event.ram_bucket,event.accelerator_class,event.route,event.router_mode,event.router_version,event.selection_reason_code,event.quant??"",event.complexity_bucket,event.tool_intensity_bucket],
  doubles:[1,event.tool_calls,event.edit_attempts,event.latency_ms??0,event.input_tokens??0,event.output_tokens??0,event.cost_usd??0,event.predicted_success_selected??0,event.validator_passed===true?1:0,event.escalated?1:0],
  indexes:["locdex-v1"]
 });
}
export default {
 async fetch(request,env){
  const url=new URL(request.url);
  if(url.pathname==="/health"&&request.method==="GET")return json({ok:true,service:"locdex-telemetry",schema_version:1});
  if(url.pathname!=="/v1/events")return json({error:"not_found"},404);
  if(request.method!=="POST")return json({error:"method_not_allowed"},405);
  if(env.PAUSE_INGESTION==="1")return json({error:"unavailable"},503);
  if(!request.headers.get("content-type")?.toLowerCase().startsWith("application/json"))return json({error:"content_type_required"},415);
  if(Number(request.headers.get("content-length")??0)>64000)return json({error:"too_large"},413);
  let payload;
  try{
   const bytes=await request.arrayBuffer();
   if(bytes.byteLength>64000)return json({error:"too_large"},413);
   payload=JSON.parse(new TextDecoder().decode(bytes));
  }catch{return json({error:"invalid_json"},400);}
  if(!validateBatch(payload))return json({error:"invalid_schema"},422);
  // Global budget per Cloudflare colo; no durable source identifier.
  if(env.INGEST_RATE_LIMITER){
   const limit=await env.INGEST_RATE_LIMITER.limit({key:"ingest"});
   if(!limit.success)return json({error:"rate_limited"},429);
  }
  if(!env.EVENTS_R2||!env.ANALYTICS)return json({error:"storage_not_configured"},503);
  const receivedAt=new Date().toISOString();
  const key="v1/"+receivedAt.slice(0,10)+"/"+crypto.randomUUID()+".json";
  try{
   await env.EVENTS_R2.put(key,JSON.stringify({schema_version:1,received_at:receivedAt,events:payload.events}),{httpMetadata:{contentType:"application/json"}});
  }catch{return json({error:"storage_unavailable"},503);}
  // R2 is canonical; Analytics Engine is a rebuildable projection.
  for(const event of payload.events){try{projectMetric(env.ANALYTICS,event);}catch{/* replay from R2 */}}
  return json({accepted:payload.events.length},202);
 }
};
