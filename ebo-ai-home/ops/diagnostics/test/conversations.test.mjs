import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { ConversationLog, normalizeConversation, groupConversations, readLocalConversations, conversationFilter } from '../src/conversations.mjs';

const at = Date.parse('2026-09-15T12:00:00Z');
const row = (role,id,seconds,text=id,session='s1',scope='local') => normalizeConversation({received_at:(at+seconds*1000)/1000,session_started_at:session,item_id:id,
  ...(role==='assistant'?{response_id:id}:{}),transcript:text},{role,scope});
const event = (role,id,seconds=0) => ({eventId:id,logStreamName:'assistant/task',timestamp:at+seconds*1000,message:JSON.stringify({
  event:role==='user'?'conversation.user.transcript':'conversation.assistant.output',received_at:(at+seconds*1000)/1000,item_id:id,transcript:id,session_started_at:1})});
function fixture(responses=[{events:[]}], settings={}) {
  let time=at;const invocations=[];let index=0;
  const store={value:{},save(){}};
  const log=new ConversationLog({store,targets:[{id:'cloud',aws:{containers:[{name:'realtime-assistant',logGroup:'/ebo-cloud/assistant',streamPrefix:'realtime-assistant/realtime-assistant'}]}}],
    calls:new Map([['cloud',async(args)=>{invocations.push(args);const r=responses[index++]||{events:[]};if(r instanceof Error)throw r;return r;}]]),directory:'.',settings:{bootstrapDays:1,...settings},clock:()=>time,
    readLocal:async()=>({messages:[],fingerprints:{},missing:[],invalid:0})});
  return {log,store,invocations,advance:ms=>{time+=ms;}};
}

test('normalization exposes only transcript content with internal stable identity',()=>{
  const m=normalizeConversation({event:'conversation.user.transcript',timestamp:'2026-09-15T12:00:00Z',transcript:' hello ',item_id:'one',audio_file:'secret.wav',token:'secret'}, {scope:'cloud'});
  assert.equal(m.message,'hello');assert.equal(m.at,at);assert.equal(m.audio_file,undefined);assert.equal(m.token,undefined);
  assert.equal(normalizeConversation({event:'health.snapshot',transcript:'not a conversation'}, {eventTime:at}),null);
  assert.equal(normalizeConversation({transcript:'   ',received_at:1},{role:'user'}),null);
  assert.equal(normalizeConversation({transcript:'message'},{role:'user'}),null);
});
test('newest conversation first, chronological user and assistant messages inside',()=>{
  const groups=groupConversations([row('assistant','a1',10),row('user','u2',60),row('assistant','a2',65),row('user','u1',0)]);
  assert.deepEqual(groups.map(g=>g.messages.map(m=>m.message)),[['u2','a2'],['u1','a1']]);
});
test('do not pair different sessions, environments or widely separated messages',()=>{
  const groups=groupConversations([row('user','u',0),row('assistant','late',500),row('assistant','other-session',20,'text','s2'),row('assistant','cloud',10,'text','s1','cloud')]);
  assert.equal(groups.length,4);
});
test('consecutive user turns and assistant-only messages are never silently discarded',()=>{
  const groups=groupConversations([row('assistant','solo',-20),row('user','u1',0),row('user','u2',10),row('assistant','a',20)]);
  assert.deepEqual(groups.map(g=>g.messages.map(m=>m.message)),[['u2','a'],['u1'],['solo']]);
});
test('cache deduplicates overlap and rewrites but preserves repeated spoken text',()=>{
  const f=fixture();f.log.merge([row('user','id1',0,'same'),row('user','id2',10,'same'),row('user','id1',0,'same')]);
  assert.equal(f.store.value.messages.length,2);f.log.merge([row('user','id1',0,'updated')]);assert.equal(f.store.value.messages.length,2);
  const payload=f.log.view();assert.equal(payload.groups.length,2);assert.deepEqual(Object.keys(payload.groups[0].messages[0]).sort(),['message','role','timestamp']);
});
test('empty cloud pages with tokens continue; checkpoint advances only after final page',async()=>{
  const f=fixture([{events:[],nextToken:'page2'},{events:[event('user','u')],nextToken:'page3'},{events:[event('assistant','a',10)]}]);
  await f.log.poll('aws');assert.equal(f.invocations.length,2);assert.equal(f.store.value.cloud.cloud.through,undefined);assert.equal(f.log.view().cloudCatchingUp,true);
  f.advance(300000);await f.log.poll('aws');assert.equal(f.invocations.length,3);assert.equal(f.store.value.cloud.cloud.through,at);
  assert.equal(f.invocations[2].at(-1),'page3');assert.equal(f.log.view().cloudCatchingUp,false);
  assert.deepEqual(f.log.view().groups[0].messages.map(m=>m.message),['u','a']);
});
test('cloud polling is incremental, bounded, and never triggered by browser reads',async()=>{
  const f=fixture();await f.log.poll('aws');for(let n=0;n<30;n++)f.log.view();await f.log.poll('aws');assert.equal(f.invocations.length,1);
  f.advance(300000);await f.log.poll('aws');assert.equal(f.invocations.length,2);
  const args=f.invocations[1];assert.equal(Number(args[args.indexOf('--start-time')+1]),at-600000);assert.ok(args.includes('--no-paginate'));
  assert.ok(args.includes(conversationFilter));assert.ok(args.includes('/ebo-cloud/assistant'));assert.equal(args.includes('--log-stream-names'),false);
});
test('inactive cloud uses 30-minute checks, resuming cloud shortens delay safely',async()=>{
  const f=fixture();await f.log.poll('local');f.advance(300000);await f.log.poll('stopped');assert.equal(f.invocations.length,1);
  await f.log.poll('aws');assert.equal(f.invocations.length,2);
});
test('daily request budget includes failures and survives process restart state',async()=>{
  const f=fixture([{events:[],nextToken:'next'},{events:[],nextToken:'more'}],{dailyRequestLimit:1});await f.log.poll('aws');
  assert.equal(f.invocations.length,1);assert.equal(f.log.view().cloudError,'daily_request_limit');
  f.advance(300000);await f.log.poll('aws');assert.equal(f.invocations.length,1);
  assert.equal(f.store.value.budget.requests,1);
});
test('throttling backs off without dropping cached messages or raw error disclosure',async()=>{
  const f=fixture([new Error('aws_throttled'),{events:[event('user','later')]}]);f.log.merge([row('user','saved',0)]);
  await f.log.poll('aws');assert.equal(f.log.view().cloudError,'aws_throttled');f.advance(300000);await f.log.poll('aws');assert.equal(f.invocations.length,1);
  f.advance(300000);await f.log.poll('aws');assert.equal(f.invocations.length,2);assert.equal(f.store.value.messages.length,2);
});
test('overlapping poll calls share one collection rather than multiplying AWS calls',async()=>{
  const f=fixture();await Promise.all([f.log.poll('aws'),f.log.poll('aws'),f.log.poll('aws')]);assert.equal(f.invocations.length,1);
});
test('recent messages retain priority while historical pagination resumes in spare budget',async()=>{
  const f=fixture([{events:[event('user','recent')]},{events:[],nextToken:'older-page'},
    {events:[event('user','newer',200)]},{events:[event('user','old',-172800)]}],{bootstrapDays:7});
  await f.log.poll('aws');
  const start=args=>Number(args[args.indexOf('--start-time')+1]);
  assert.equal(start(f.invocations[0]),at-86400000);
  assert.equal(start(f.invocations[1]),at-2*86400000);
  assert.equal(f.store.value.cloud.cloud.historyWindow.token,'older-page');
  f.advance(300000);await f.log.poll('aws');
  assert.equal(start(f.invocations[2]),at-600000);
  assert.equal(f.invocations[3].at(-1),'older-page');
  assert.deepEqual(f.log.view().groups.map(g=>g.messages[0].message),['newer','recent','old']);
  assert.equal(f.store.value.cloud.cloud.historyBefore,at-2*86400000);
});
test('cloud transcript fragments survive persisted state and join without losing spaces',()=>{
  const f=fixture();
  const part=(index,text)=>normalizeConversation({event:'conversation.assistant.output',event_id:'fragmented',received_at:at/1000,
    response_id:'response',transcript:text,chunk_count:3,chunk_index:index},{scope:'cloud:task'});
  f.log.merge([part(2,'world'),part(0,'hello')]);
  assert.equal(f.log.view().groups.length,0);assert.equal(f.log.view().partialMessages,1);
  f.store.value=JSON.parse(JSON.stringify(f.store.value));
  f.log.merge([part(1,' ')]);
  assert.equal(f.log.view().groups[0].messages[0].message,'hello world');assert.equal(f.log.view().partialMessages,0);
  f.log.merge([part(0,'hello'),part(1,' '),part(2,'world')]);assert.equal(f.store.value.messages.length,1);
});
test('fragment identity does not depend on arrival order or CloudWatch wrapper IDs',()=>{
  const f=fixture();
  const part=(i)=>normalizeConversation({event:'conversation.assistant.output',event_id:'same-logical-event',received_at:at/1000,
    transcript:i?'world':'hello ',chunk_count:2,chunk_index:i},{scope:'cloud:task',eventId:'wrapper-'+i});
  f.log.merge([part(1),part(0)]);f.log.merge([part(0),part(1)]);
  assert.equal(f.store.value.messages.length,1);assert.equal(f.store.value.messages[0].message,'hello world');
});
test('local files tolerate malformed/partial lines and re-read replacements',async t=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ebo-conversations-'));t.after(async()=>{
    assert.equal(path.dirname(path.resolve(dir)),path.resolve(os.tmpdir()));assert.ok(path.basename(dir).startsWith('ebo-conversations-'));await fs.rm(dir,{recursive:true,force:true});
  });
  const file=path.join(dir,'transcripts.jsonl');const line=JSON.stringify({received_at:at/1000,item_id:'u',transcript:'hello'});
  await fs.writeFile(file,line+'\nnot-json\n{"partial"');
  const a=await readLocalConversations(dir);assert.equal(a.messages.length,1);assert.equal(a.invalid,1);assert.equal(a.fingerprints['transcripts.jsonl'],undefined);
  await fs.writeFile(file,line+'\n');const b=await readLocalConversations(dir,a.fingerprints);assert.equal(b.messages.length,1);
  const c=await readLocalConversations(dir,b.fingerprints);assert.equal(c.messages.length,0);
  await fs.writeFile(file,line.replace('hello','revised message')+'\n');assert.equal((await readLocalConversations(dir,b.fingerprints)).messages[0].message,'revised message');
  assert.deepEqual(a.missing,['assistant_outputs.jsonl']);
});
