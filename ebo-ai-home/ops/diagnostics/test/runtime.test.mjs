import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { RuntimeControl } from '../src/runtime.mjs';
import { createRuntimeIO } from '../src/runtime-io.mjs';
import { createAwsCli } from '../src/aws-cli.mjs';
import { activeTargets } from '../src/environment.mjs';
import { observe } from '../src/probes.mjs';
import { Controllers } from '../src/controllers.mjs';
import { dashboardData, dashboardHtml, serveDashboard } from '../src/dashboard.mjs';
import { awsPolicies } from '../src/aws-policy.mjs';
import fs from 'node:fs';
import vm from 'node:vm';
import http from 'node:http';

const memory = value => ({ value, save() {} });
const cloud = JSON.parse(fs.readFileSync(new URL('../aws-target.example.json', import.meta.url)));
const base = JSON.parse(fs.readFileSync(new URL('../config.example.json', import.meta.url)));
function fixture() {
  const calls = [];
  const actual = { observedAt: 1000, local: { known: true, stopped: true, containers: [] }, cloud: { known: true, stopped: true, services: [] } };
  const io = Object.fromEntries(['stopLocal','stopCloud','startLocal','startCloud','waitHealthy'].map(k => [k, async () => calls.push(k)]));
  io.inspect = async () => actual; io.matches = () => true;
  const store = memory({}); const config = { ...base, runtimeEnvironment: 'aws', targets: [...base.targets, cloud] };
  const runtime = new RuntimeControl(store, config, io, () => 1000);
  return { runtime, store, config, io, actual, calls };
}
test('all three choices persist before writes and stop the previous side before starting', async () => {
  for (const [mode, expected] of [['aws',['stopLocal','startCloud','waitHealthy']],['local',['stopCloud','startLocal','waitHealthy']],['stopped',['stopLocal','stopCloud']]]) {
    const f = fixture();
    f.io[expected[0]] = async () => { assert.equal(f.store.value.desired, mode); assert.equal(f.store.value.phase, 'switching'); f.calls.push(expected[0]); };
    assert.equal(f.runtime.request(mode).code, 202); await f.runtime.pending;
    assert.deepEqual(f.calls, expected); assert.equal(f.store.value.phase, 'ready'); assert.equal(f.config.runtimeEnvironment, mode);
  }
});
test('failed or uncertain shutdown prevents the other side from starting', async () => {
  for (const mode of ['local','aws']) {
    const f = fixture(); f.io[mode === 'local' ? 'stopCloud' : 'stopLocal'] = async () => { throw new Error('aws_stop_unverified'); };
    f.runtime.request(mode); await f.runtime.pending;
    assert.equal(f.store.value.phase, 'failed'); assert.equal(f.calls.length, 0); assert.equal(f.runtime.status().monitoringSuppressed, true);
  }
});
test('stop everywhere still attempts cloud stop when Docker is unreachable', async () => {
  const f = fixture(); f.io.stopLocal = async () => { throw new Error('docker_unavailable'); };
  f.runtime.request('stopped'); await f.runtime.pending;
  assert.deepEqual(f.calls, ['stopCloud']); assert.equal(f.store.value.error, 'docker_unavailable');
  assert.equal(f.store.value.steps[0].status, 'failed'); assert.equal(f.store.value.phase, 'failed');
});
test('a lifecycle operation cannot overlap another operation or an automatic repair', async () => {
  const f = fixture(); let release; f.io.stopCloud = () => new Promise(r => { release = r; });
  f.runtime.request('local'); assert.equal(f.runtime.request('aws').code, 409);
  await assert.rejects(f.runtime.repair(async () => assert.fail()), /runtime_busy/);
  release(); await f.runtime.pending;
  const p = f.runtime.repair(() => new Promise(r => { release = r; }));
  assert.equal(f.runtime.request('aws').code, 409); release(); await p;
});
test('stop during switching is durable, prevents the pending start, then serially stops both sides', async () => {
  const f=fixture();let release;let n=0;
  f.io.stopLocal=async()=>{f.calls.push('stopLocal');if(n++===0)await new Promise(r=>{release=r;});};
  f.runtime.request('aws');const first=f.runtime.pending;
  assert.equal(f.runtime.request('stopped').code,202);assert.equal(f.store.value.queuedMode,'stopped');
  assert.equal(f.runtime.status().desired,'stopped');assert.equal(f.config.runtimeEnvironment,'stopped');
  release();await first;await f.runtime.pending;
  assert.deepEqual(f.calls,['stopLocal','stopLocal','stopCloud']);assert.equal(f.store.value.desired,'stopped');assert.equal(f.store.value.phase,'ready');
});
test('stop interrupts a long health wait without waiting for its timeout', async () => {
  const f=fixture();let release;
  f.io.waitHealthy=async(mode,onSample)=>{await new Promise(r=>{release=r;});onSample([]);};
  f.runtime.request('aws');const first=f.runtime.pending;await new Promise(r=>setImmediate(r));
  assert.equal(typeof release,'function');f.runtime.request('stopped');release();await first;await f.runtime.pending;
  assert.equal(f.store.value.phase,'ready');assert.equal(f.store.value.desired,'stopped');assert.ok(f.calls.includes('stopCloud'));
});
test('restart retains desired stop and marks interrupted transition honestly', () => {
  const f = fixture(); Object.assign(f.store.value, { desired: 'stopped', phase: 'switching' });
  const resumed = new RuntimeControl(f.store, f.config, f.io);
  assert.equal(resumed.status().error, 'runtime_interrupted'); assert.deepEqual(activeTargets(f.config), []);
});
test('health timeout permits diagnostics without claiming successful switching', async () => {
  const f = fixture(); f.io.waitHealthy = async () => { throw new Error('runtime_health_timeout'); };
  f.runtime.request('aws'); await f.runtime.pending;
  assert.equal(f.runtime.status().phase, 'failed'); assert.equal(f.runtime.status().monitoringSuppressed, false);
});
test('first migration is read-only; explicit stop subsequently enforces inactive shutdown', async () => {
  const f = fixture(); f.actual.local.stopped = false; f.actual.cloud.stopped = false;
  await f.runtime.poll(); assert.deepEqual(f.calls, []);
  f.runtime.request('stopped'); await f.runtime.pending; f.calls.length = 0;
  await f.runtime.poll(); assert.deepEqual(f.calls, ['stopLocal','stopCloud']);
});
test('only selected active environment is restored after unexpected stop, once per budget', async () => {
  const f = fixture(); Object.assign(f.store.value,{desired:'local',phase:'ready'});
  f.actual.local.containers=[{status:'exited'}]; f.config.autoRecovery=true; f.config.observationOnly=false;
  await f.runtime.poll(); await f.runtime.pending;
  assert.deepEqual(f.calls,['stopCloud','startLocal','waitHealthy']); assert.equal(f.store.value.source,'automatic_restore');
  f.calls.length=0; await f.runtime.poll(); assert.deepEqual(f.calls,[]);
  f.store.value.desired='stopped'; await f.runtime.poll(); assert.deepEqual(f.calls,[]);
});
test('authenticated host intent switches watcher without restarting and cancels old jobs', async () => {
  const f = fixture(); const cancelled = [];
  const store = memory({ scopes: { assistant: { incident: { id:'old', jobSubmitted:true }, history: [] } } });
  const controller = new Controllers(store, f.config, { cancel: async id => cancelled.push(id) });
  const sample = await observe(f.config, { snapshot: async () => ({ runtimeEnvironment: 'stopped', runtime: { controlVersion: 1, desired: 'stopped', monitoringSuppressed: true } }) });
  await controller.tick(sample, 1000);
  assert.equal(sample.code, 'project_stopped'); assert.equal(store.value.runtimeEnvironment, 'stopped');
  assert.deepEqual(store.value.activeTargets, []); assert.deepEqual(cancelled, ['old']);
});
test('dashboard never reports stale, mismatched or failed transitions as healthy', () => {
  const f = fixture(); f.runtime.actual = f.actual; f.store.value.phase = 'ready'; f.store.value.desired = 'stopped';
  assert.equal(dashboardData(f.runtime, null, 1000).tone, 'healthy');
  assert.equal(dashboardData(f.runtime, null, 1200).tone, 'attention');
  f.io.matches = () => false; assert.equal(dashboardData(f.runtime, null, 1000).tone, 'attention');
  f.io.matches = () => true; f.store.value.phase = 'failed'; assert.equal(dashboardData(f.runtime, null, 1000).tone, 'attention');
});
test('dashboard presents advanced diagnosis and recommendations linked to the incident', () => {
  const f = fixture(); const d = dashboardData(f.runtime, { incidents: { i: { id: 'i', code:'stalled' } }, providers: { 'diagnostic-service': { jobs: [{ id:'i',result:{ advanced:{ diagnosis:{summary:'原因',recommendations:['检查连接']} } } }] } } });
  assert.equal(d.events[0].summary, '原因'); assert.deepEqual(d.events[0].recommendations, ['检查连接']);
  const script = dashboardHtml('test').match(/<script[^>]*>([\s\S]*)<\/script>/)[1];
  assert.doesNotThrow(() => new vm.Script(script));
});
test('dashboard defaults to English and offers a remembered Chinese switch', () => {
  const html=dashboardHtml('test');
  assert.match(html,/<html lang="en">/);assert.match(html,/<option value="en">English<\/option><option value="zh">中文<\/option>/);
  assert.match(html,/ebo-dashboard-language/);assert.match(html,/Runtime & Diagnostics/);assert.match(html,/运行与诊断/);
});
test('dashboard accepts only loopback host, same-origin CSRF-authenticated JSON writes', async t => {
  const f = fixture(); const server = serveDashboard({ runtime:f.runtime, reportDir: 'nonexistent', config:f.config, awsHost:{ connections:{} }, port:0 });
  await once(server, 'listening'); t.after(() => server.close());
  const origin = `http://127.0.0.1:${server.address().port}`;
  const html = await (await fetch(origin)).text(); const csrf = html.match(/const csrf="([a-f0-9]+)"/)[1];
  const badHost = await new Promise(resolve => http.get(origin+'/api/status', {headers:{host:'evil.invalid'}}, res => {res.resume();resolve(res.statusCode);}));
  assert.equal(badHost,403);
  assert.equal((await fetch(origin+'/api/runtime',{method:'POST',headers:{'content-type':'application/json'},body:'{"mode":"stopped"}'})).status,403);
  const headers = { origin, 'content-type':'application/json', 'x-ebo-csrf':csrf };
  assert.equal((await fetch(origin+'/api/runtime',{method:'POST',headers,body:'{"mode":"both"}'})).status,400);
  assert.equal((await fetch(origin+'/api/runtime',{method:'POST',headers,body:'{"mode":"stopped"}'})).status,202);
  await f.runtime.pending;
});

test('conversation endpoint reads cached view only and rejects foreign hosts', async t => {
  const f=fixture();const limits=[];
  const conversations={view(limit){limits.push(limit);return {groups:[{id:'group',messages:[{timestamp:'2026-09-15T12:00:00Z',role:'user',message:'<script>text only</script>'}]}]};},poll(){throw Error('must not collect from HTTP');}};
  const server=serveDashboard({runtime:f.runtime,reportDir:'nonexistent',config:f.config,awsHost:{connections:{}},conversations,port:0});
  await once(server,'listening');t.after(()=>server.close());
  const origin=`http://127.0.0.1:${server.address().port}`;
  const response=await fetch(origin+'/api/conversations?limit=100');
  assert.equal(response.status,200);assert.match(response.headers.get('cache-control'),/no-store/);
  const payload=await response.json();assert.equal(payload.groups[0].messages[0].message,'<script>text only</script>');
  assert.deepEqual(limits,[100]);
  const denied=await new Promise(resolve=>http.get(origin+'/api/conversations',{headers:{host:'untrusted.example'}},res=>{res.resume();resolve(res.statusCode);}));
  assert.equal(denied,403);assert.deepEqual(limits,[100]);
});

function ioFixture() {
  let at = 1000; const writes = []; let desired = 1; let running = 1; let stopping = false;
  const local = new Map(base.targets.map(t => [t.container, 'running']));
  const call = async (args, options) => {
    const op = args.slice(0,2).join(' ');
    if (op === 'sts get-caller-identity') return { Account:cloud.aws.accountId, Arn:'arn:aws:iam::'+cloud.aws.accountId+':user/controller' };
    if (op === 'ecs describe-services') return {services:[{ serviceName:cloud.aws.service, status:'ACTIVE',launchType:'FARGATE',desiredCount:desired,runningCount:running,pendingCount:0 }]};
    if (op === 'application-autoscaling describe-scalable-targets') return { ScalableTargets:[] };
    if (op === 'ecs list-tasks') return {taskArns: (stopping ? args.includes('STOPPED') : running && args.includes('RUNNING')) ? ['arn:task/one'] : []};
    if (op === 'ecs describe-tasks') return { tasks:[{taskArn:'arn:task/one',lastStatus:stopping?'STOPPING':'RUNNING'}] };
    if (op === 'ecs update-service') { writes.push({args,options}); desired=Number(args.at(-1)); running=desired; return {}; }
    throw new Error(op);
  };
  const docker = async args => {
    if (args[0] === 'info') return {stdout:'1'};
    if (args[0] === 'inspect') return {stdout:JSON.stringify({Status:local.get(args.at(-1))})};
    writes.push({args});
    if (args[0] === 'stop') local.set(args.at(-1),'exited');
    return {stdout:''};
  };
  const config = { ...base, targets:[...base.targets,cloud] };
  const calls = new Map([[cloud.id,call]]);
  const io = createRuntimeIO({ config,docker,calls,adapters:new Map(),projectRoot:'.',clock:()=>at,pause:async()=>{at+=100;} });
  return { io,writes,calls,call,local,setStopping:()=>{stopping=true;},setCloudStopped:()=>{desired=0;running=0;} };
}
test('local shutdown disables all restart policies and verifies every business container', async () => {
  const f=ioFixture(); await f.io.stopLocal(); assert.equal((await f.io.inspect()).local.stopped,true);
  assert.equal(f.writes.filter(x=>x.args[0]==='update'&&x.args[1]==='--restart=no').length,3);
});
test('cloud shutdown sets desiredCount zero, never stop-task, and waits for STOPPING tasks', async () => {
  const f=ioFixture(); f.setStopping();
  await assert.rejects(f.io.stopCloud(),/aws_stop_unverified/);
  assert.equal(f.writes.length,1); assert.equal(f.writes[0].args[1],'update-service'); assert.equal(f.writes[0].args.at(-1),'0');
  await assert.rejects(f.io.startLocal(),/aws_stop_unverified/);
});
test('autoscaling must be suspended and wrong AWS identity blocks all writes', async () => {
  for (const kind of ['scaling','identity']) {
    const f=ioFixture(); f.calls.set(cloud.id,async(args,opts)=>{
      if(kind==='identity'&&args[0]==='sts')return {Account:'wrong'};
      if(kind==='scaling'&&args[0]==='application-autoscaling')return {ScalableTargets:[{SuspendedState:{}}]};
      return f.call(args,opts);
    });
    await assert.rejects(f.io.stopCloud(),new RegExp(kind==='identity'?'account_mismatch':'autoscaling_enabled')); assert.equal(f.writes.length,0);
  }
});
test('AWS command capability limits runtime writes to the configured service and 0 or 1', async () => {
  const seen=[]; const c=createAwsCli({controlProfile:'control',allowRuntimeControl:true},cloud,async(...args)=>{seen.push(args);return {stdout:'{}'};});
  const cmd=['ecs','update-service','--cluster',cloud.aws.cluster,'--service',cloud.aws.service,'--desired-count','0'];
  await c(cmd,{control:true}); assert.ok(seen[0][1].includes('control'));
  await assert.rejects(c(cmd)); await assert.rejects(c([...cmd.slice(0,-1),'2'],{control:true}));
  await assert.rejects(c([...cmd,'--force-new-deployment'],{control:true}));
  const changed=[...cmd];changed[5]='another-service';await assert.rejects(c(changed,{control:true}));
  const p=awsPolicies(cloud).control;assert.deepEqual(p.Statement.find(s=>s.Sid==='SetConfiguredServiceCount').Action,['ecs:UpdateService']);
});
