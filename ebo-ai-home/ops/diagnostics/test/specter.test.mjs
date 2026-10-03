import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { classifyHealth, healthEvidence } from '../src/probes.mjs';
import { createAssistantControl } from '../src/assistant-control.mjs';
import { normalizeConversation } from '../src/conversations.mjs';
import { serveDashboard } from '../src/dashboard.mjs';
import { once } from 'node:events';
const target={id:'assistant',restartOnStall:true}, config={startupSeconds:90};
const healthy={health_contract_version:2,ok:true,uptime_seconds:500,listener_ready:true,mqtt_connected:true,
 frigate_ready:true,face_library_ready:true,session_state:'standby',realtime_connected:false,
 video_streaming:true,audio_streaming:true,source_audio_status:'receiving',source_audio_ok:true};

test('waiting for family without enrolled faces or Realtime is a healthy standby',()=>{
 const h=classifyHealth({...healthy,profiles:[{enrolled_images:0}]},target,config);
 assert.equal(h.status,'healthy');assert.equal(h.code,'awaiting_family');assert.equal(h.recoverable,false);
});
test('Frigate and MQTT faults are diagnosed without restarting the assistant blindly',()=>{
 for(const [key,code] of [['mqtt_connected','frigate_mqtt_disconnected'],['frigate_ready','frigate_camera_unavailable']]){
  const h=classifyHealth({...healthy,ok:false,[key]:false},target,config);
  assert.equal(h.status,'fault');assert.equal(h.code,code);assert.equal(h.recoverable,false);
 }
});
test('held Frigate frames cannot hide a stale robot source',()=>{
 const h=classifyHealth({...healthy,ok:false,engine_video_monitor_enabled:true,source_video_ok:false,
  source_video_status:'source_stale'},target,config);
 assert.equal(h.code,'source_video_unconfirmed');assert.equal(h.recoverable,false);
 assert.equal(h.evidence.source_video_status,'source_stale');
});
test('audio-first assistant stays healthy through visual and Frigate MQTT failures',()=>{
 const h={...healthy,health_contract_version:3,visual_required:false,audio_ready:true};
 for(const change of [{video_streaming:false,frigate_ready:false},{mqtt_connected:false},
   {video_streaming:false,source_video_ok:false,engine_video_monitor_enabled:true,source_video_status:'source_stale'}]){
  const result=classifyHealth({...h,...change},target,config);
  assert.equal(result.status,'healthy');assert.equal(result.recoverable,false);
 }
 assert.equal(classifyHealth({...h,ok:false,source_audio_ok:false},target,config).code,'source_audio_unconfirmed');
 assert.equal(classifyHealth({...h,audio_streaming:false,ok:false},target,config).code,'audio_transport_stalled');
 assert.equal(classifyHealth({...h,session_state:'active',realtime_connected:false,ok:false},target,config).code,'realtime_disconnected');
 assert.equal(classifyHealth({...h,visual_required:true},target,config).code,'health_contract_invalid');
});
test('standby cannot hide real source-audio loss and active disconnects',()=>{
 assert.equal(classifyHealth({...healthy,ok:false,source_audio_status:'no_source_packets',source_audio_ok:false},target,config).code,'source_audio_unconfirmed');
 assert.equal(classifyHealth({...healthy,ok:false,session_state:'active'},target,config).code,'realtime_disconnected');
 assert.equal(classifyHealth({...healthy,ok:false,session_state:'connecting'},target,config).status,'grace');
});
test('diagnostic evidence contains state but no family identity or memory contents',()=>{
 const evidence=healthEvidence({...healthy,active_user:'father',memory_content:'private',profiles:[{name:'private'}]});
 assert.equal(evidence.session_state,'standby');assert.equal(evidence.health_contract_version,2);
 assert.equal(evidence.active_user,undefined);assert.equal(evidence.memory_content,undefined);assert.equal(evidence.profiles,undefined);
});
test('control credential is loaded only in backend and cloud runtime refuses local sessions',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ebo-control-'));
 try{
  const envFile=path.join(dir,'.env');fs.writeFileSync(envFile,'EBO_API_TOKEN=private-token\nOPENAI_API_KEY=never-forward\n');
  let desired='local',sent;
  const control=createAssistantControl({runtime:{busy:false,status:()=>({desired})},envFile,fetchImpl:async(url,options)=>{
   sent={url,options};return {status:202,json:async()=>({accepted:true})};
  }});
  const response=await control.command('start',{user_id:'father',url:'http://untrusted'});
  assert.equal(response.code,202);assert.equal(sent.url,'http://127.0.0.1:8099/session/start');
  assert.equal(sent.options.headers['X-EBO-Control-Token'],'private-token');
  assert.equal(sent.options.body,'{"user_id":"father"}');assert.ok(!JSON.stringify(response).includes('private-token'));
  desired='aws';assert.equal((await control.command('start',{user_id:'father'})).code,409);
 }finally{fs.rmSync(dir,{recursive:true});}
});
test('new transcripts preserve Realtime source and parent identifier',()=>{
 const m=normalizeConversation({event:'conversation.user.transcript',source:'realtime',user_id:'father',received_at:1000,item_id:'one',transcript:'hello'}, {scope:'local'});
 assert.equal(m.source,'realtime');assert.equal(m.user_id,'father');
});

test('intentional AI pause stays healthy and never requests a restart',()=>{
 const result=classifyHealth({...healthy,assistant_enabled:false,session_state:'paused'},target,config);
 assert.equal(result.status,'healthy');assert.equal(result.code,'assistant_paused');assert.equal(result.recoverable,false);
 assert.equal(result.evidence.assistant_enabled,false);
});

test('dashboard pause and resume use authenticated assistant controls without changing runtime',async t=>{
 const commands=[];
 const runtime={request(){throw Error('must not change container lifecycle');}};
 const assistantControl={command:async(action,body)=>{commands.push([action,body]);return {code:200,body:{accepted:true}};}};
 const server=serveDashboard({runtime,assistantControl,reportDir:'nonexistent',config:{targets:[]},awsHost:{connections:{}},port:0});
 await once(server,'listening');t.after(()=>server.close());
 const origin=`http://127.0.0.1:${server.address().port}`;
 const html=await (await fetch(origin)).text();const csrf=html.match(/const csrf="([a-f0-9]+)"/)[1];
 assert.match(html,/id="assistantPause"/);assert.match(html,/id="assistantResume"/);
 for(const action of ['pause','resume']){
  const url=origin+'/api/assistant/'+action;
  assert.equal((await fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:'{}'})).status,403);
  assert.equal((await fetch(url,{method:'POST',headers:{origin,'content-type':'application/json','x-ebo-csrf':csrf},body:'{}'})).status,200);
 }
 assert.deepEqual(commands,[['pause',{}],['resume',{}]]);
});

test('backend maps AI toggles to fixed assistant endpoints and keeps credentials private',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ebo-ai-toggle-'));
 try{
  const envFile=path.join(dir,'.env');fs.writeFileSync(envFile,'EBO_API_TOKEN=private-token\n');
  const sent=[];
  const control=createAssistantControl({runtime:{busy:false,status:()=>({desired:'local'})},envFile,fetchImpl:async(url,options)=>{
   sent.push({url,options});return {status:200,json:async()=>({accepted:true})};
  }});
  for(const action of ['pause','resume'])assert.equal((await control.command(action,{mode:'stopped',url:'http://untrusted'})).code,200);
  assert.deepEqual(sent.map(s=>s.url),['http://127.0.0.1:8099/assistant/pause','http://127.0.0.1:8099/assistant/resume']);
  assert.ok(sent.every(s=>s.options.body==='{}'&&s.options.headers['X-EBO-Control-Token']==='private-token'));
 }finally{fs.rmSync(dir,{recursive:true});}
});
