import test from "node:test";
import assert from "node:assert/strict";
import handler, { validateBatch, validateEvent } from "../src/index.mjs";

const event = {
 event:"routing_outcome",router_version:"rules-v0",
 task_class:"bug_fix",language:"python",repo_size_bucket:"small",
 requested_change:"single_file_or_unknown",estimated_files:1,dependency_fanout:1,
 has_tests:true,has_stacktrace:false,context_tokens:1234,
 complexity_bucket:"medium",tool_intensity_bucket:"low",model_id:"qwen",
 backend:"local",quant:"q4",os:"windows",ram_bucket:"16gb_class",
 accelerator_class:"cpu",input_tokens:null,output_tokens:null,latency_ms:50,
 tool_calls:2,edit_attempts:1,compile_passed:true,tests_passed:true,
 lint_passed:null,validator_passed:true,escalated:false,user_reverted:false,
 selected_model:"qwen",selection_reason_code:"local_likely_success",
 predicted_success_selected:0.8,prediction_gap_bucket:null,
 fallback_model:null,route:"local",router_mode:"balanced",cost_usd:0,
};

function fixture() {
 const objects=[];
 const points=[];
 const env={
  EVENTS_R2:{async put(key,data){objects.push({key,body:JSON.parse(data)});}},
  ANALYTICS:{writeDataPoint(point){points.push(point);}},
  INGEST_RATE_LIMITER:{async limit(){return {success:true};}},
  PAUSE_INGESTION:"0",
 };
 const request=(value,headers={})=>new Request("https://test.example/v1/events",{
  method:"POST",
  headers:{"content-type":"application/json",...headers},
  body:typeof value==="string"?value:JSON.stringify(value),
 });
 return {env,objects,points,request};
}

test("strict valid event and batch accepted",()=>{
 assert.equal(validateEvent(event),true);
 assert.equal(validateBatch({schema_version:1,events:[event]}),true);
});
test("unknown fields, prompts, and paths fail closed",()=>{
 assert.equal(validateEvent({...event,prompt:"secret"}),false);
 assert.equal(validateEvent({...event,model_id:"C:/Users/Somebody"}),false); // too long identifiers can be rejected
 assert.equal(validateEvent({...event,model_id:"../../secret"}),false);
 assert.equal(validateEvent({...event,task_class:"private source code"}),false);
});
test("typed fields and batch cap enforced",()=>{
 assert.equal(validateEvent({...event,tool_calls:"2"}),false);
 assert.equal(validateEvent({...event,latency_ms:Infinity}),false);
 assert.equal(validateBatch({schema_version:1,events:Array(26).fill(event)}),false);
});
test("worker stores only accepted anonymous schema and writes projection",async()=>{
 const f=fixture();
 const response=await handler.fetch(f.request({schema_version:1,events:[event]}),f.env);
 assert.equal(response.status,202);
 assert.equal(f.objects.length,1);
 assert.equal(f.objects[0].body.events.length,1);
 assert.equal(f.points.length,1);
 assert.equal(f.points[0].indexes[0],"locdex-v1");
 assert.equal(f.points[0].blobs.length<=20,true);
});
test("invalid payload cannot reach storage",async()=>{
 const f=fixture();
 const response=await handler.fetch(f.request({schema_version:1,events:[{...event,prompt:"hello"}]}),f.env);
 assert.equal(response.status,422);
 assert.equal(f.objects.length,0);
});
test("paused ingestion and rate limit are enforced",async()=>{
 const f=fixture();
 f.env.PAUSE_INGESTION="1";
 assert.equal((await handler.fetch(f.request({schema_version:1,events:[event]}),f.env)).status,503);
 f.env.PAUSE_INGESTION="0";
 f.env.INGEST_RATE_LIMITER={async limit(){return {success:false};}};
 assert.equal((await handler.fetch(f.request({schema_version:1,events:[event]}),f.env)).status,429);
});
test("R2 failure rejects ingestion without claiming success",async()=>{
 const f=fixture();
 f.env.EVENTS_R2={async put(){throw new Error("down")}};
 assert.equal((await handler.fetch(f.request({schema_version:1,events:[event]}),f.env)).status,503);
});
