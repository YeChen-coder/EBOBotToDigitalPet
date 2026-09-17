import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { validateAwsTarget } from '../src/aws-config.mjs';
import { classifyAws } from '../src/aws-health.mjs';
import { AwsEcsAdapter } from '../src/aws-ecs.mjs';
import { createAwsCli } from '../src/aws-cli.mjs';
import { observe } from '../src/probes.mjs';
import { Controller } from '../src/controller.mjs';
import { Controllers } from '../src/controllers.mjs';
import { ActionBridge } from '../src/bridge.mjs';
import { awsPolicies } from '../src/aws-policy.mjs';

const target = validateAwsTarget(JSON.parse(fs.readFileSync(new URL('../aws-target.example.json', import.meta.url))));
const config = { runtimeEnvironment: 'aws', targets: [target], autoRecovery: true, observationOnly: false, startupSeconds: 90,
  confirmSeconds: 60, recoverySeconds: 120, healthySeconds: 30, repeatWindowSeconds: 1800, diagnosisSeconds: 300, notifySeconds: 300 };
const healthy = { ok: true, realtime_connected: true, video_streaming: true, audio_streaming: true, source_audio_ok: true, source_audio_status: 'receiving' };
const arn = `arn:aws:ecs:ca-central-1:${target.aws.accountId}:task/ebo-cloud-lab/task-a`;
const memory = (value = {}) => ({ value, save() {} });
function fixture() {
  let at = 1000; const calls = [];
  const service = { desiredCount: 1, runningCount: 1, pendingCount: 0, deployments: [{ rolloutState: 'COMPLETED' }], deploymentConfiguration: { minimumHealthyPercent: 0, maximumPercent: 100 } };
  const task = { taskArn: arn, lastStatus: 'RUNNING', desiredStatus: 'RUNNING', healthStatus: 'HEALTHY', startedAt: 1,
    containers: target.aws.containers.map(c => ({ name: c.name, lastStatus: 'RUNNING', healthStatus: 'HEALTHY' })) };
  const connection = { readProfile: 'reader', actionProfile: 'executor', allowTaskReplacement: true };
  const call = async (args, options) => {
    calls.push({ args, options });
    switch (args.slice(0, 2).join(' ')) {
      case 'sts get-caller-identity': return { Account: target.aws.accountId, Arn: 'arn:aws:iam::123456789012:user/reader' };
      case 'ecs describe-services': return { services: [service] };
      case 'ecs list-tasks': return { taskArns: [task.taskArn] };
      case 'ecs describe-tasks': return { tasks: [task] };
      case 'logs filter-log-events': {
        const engine = args.includes('/ebo-cloud/engine');
        return { events: [{ timestamp: at * 1000, message: JSON.stringify({ schema_version: 1, timestamp: new Date(at * 1000).toISOString(),
          service: engine ? 'ebo-engine' : 'realtime-assistant', event: 'health.snapshot', health: engine ? { robot_count: 1 } : healthy }) }] };
      }
      case 'ecs stop-task': return {};
      default: return { Datapoints: [] };
    }
  };
  const t = structuredClone(target); t.restartOnStall = true;
  const adapter = new AwsEcsAdapter(t, config, connection, memory(), call, () => at);
  return { adapter, calls, service, task, connection, call, setAt: v => { at = v; } };
}

test('AWS target validates timing, resource names and container contracts', () => {
  assert.throws(() => validateAwsTarget({ ...target, aws: { ...target.aws, pollSeconds: 1 } }));
  assert.throws(() => validateAwsTarget({ ...target, aws: { ...target.aws, cluster: '--other-account' , accountId: 'x' } }));
});
test('live-shaped ECS and CloudWatch data becomes business health, without raw logs', async () => {
  const f = fixture(); f.service.events = [{ createdAt: 900, message: 'unable to assume role SECRET household detail' }];
  await f.adapter.refresh(true); const s = f.adapter.snapshot();
  assert.equal(s.observation.code, 'aws_business_healthy');
  assert.equal(s.health['ebo-engine'].health.robot_count, 1);
  assert.equal(s.serviceEvents[0].category, 'task_role_failure'); assert.equal(JSON.stringify(s).includes('SECRET'), false);
  assert.ok(f.calls.filter(x => x.args[0] === 'logs').every(x => x.args.includes(`ebo-engine/ebo-engine/task-a`) || x.args.includes(`realtime-assistant/realtime-assistant/task-a`)));
});
test('expired or wrong-task health never passes or triggers restart/model', async () => {
  const f = fixture(); await f.adapter.refresh(true);
  const s = f.adapter.snapshot(); s.health['realtime-assistant'].taskArn = 'old-task';
  assert.equal(classifyAws(s, target, config, 1000).diagnosticEligible, false);
  f.setAt(1400); assert.equal(f.adapter.snapshot().observation.code, 'aws_snapshot_stale');
});
test('account mismatch and root credentials fail closed', async () => {
  const f = fixture(); f.adapter.call = async () => ({ Account: '000000000000' });
  await f.adapter.refresh(true); assert.equal(f.adapter.snapshot().observation.code, 'aws_account_mismatch');
  f.adapter.call = async () => ({ Account: target.aws.accountId, Arn: 'arn:aws:iam::123456789012:root' });
  await f.adapter.refresh(true); assert.equal(f.adapter.snapshot().observation.code, 'aws_root_identity_refused');
});
test('bounded ECS self-healing becomes diagnosis only after its deadline', async () => {
  const f = fixture(); f.task.healthStatus = 'UNHEALTHY';
  await f.adapter.refresh(true); assert.equal(f.adapter.snapshot().observation.status, 'grace');
  f.setAt(1299); await f.adapter.refresh(true); assert.equal(f.adapter.snapshot().observation.status, 'grace');
  f.setAt(1300); await f.adapter.refresh(true); const o = f.adapter.snapshot().observation;
  assert.equal(o.code, 'aws_scheduler_recovery_failed'); assert.equal(o.recoverable, false);
});
test('desired zero suppresses and overlapping Tasks are faults without replacement', async () => {
  const f = fixture(); f.service.desiredCount = 0; await f.adapter.refresh(true);
  assert.equal(f.adapter.snapshot().observation.status, 'suppressed');
  f.service.desiredCount = 2; await f.adapter.refresh(true);
  assert.equal(f.adapter.snapshot().observation.code, 'aws_single_input_overlap');
});
test('health log pagination handles empty pages and refuses incomplete health', async () => {
  const f = fixture(); const base = f.adapter.call; let pages = 0;
  f.adapter.call = async (args, options) => {
    if (args[0] === 'logs') { pages++; return { events: [], nextToken: `page-${pages}` }; }
    return base(args, options);
  };
  await f.adapter.refresh(true); const s = f.adapter.snapshot();
  assert.equal(pages, target.aws.containers.length * target.aws.maxLogPages);
  assert.equal(s.collectionErrors.length, 2); assert.equal(s.observation.code, 'aws_health_telemetry_stale');
});
test('replacement rechecks exact task and never force-deploys an unexpected new task', async () => {
  const f = fixture(); f.task.taskArn = arn + '-changed';
  await assert.rejects(f.adapter.restart({ taskArn: arn }), /precondition_changed/);
  assert.equal(f.calls.some(x => x.args[1] === 'stop-task'), false);
  f.task.taskArn = arn; await f.adapter.restart({ taskArn: arn });
  assert.equal(f.calls.filter(x => x.args[1] === 'stop-task').length, 1);
  assert.ok(f.calls.at(-1).options.action);
});
test('replacement refuses deployments, overlap settings and scaled-down services', async () => {
  for (const mutate of [f => { f.service.pendingCount = 1; }, f => { f.service.desiredCount = 0; },
    f => { f.service.deploymentConfiguration.maximumPercent = 200; }, f => { f.service.deployments[0].rolloutState = 'IN_PROGRESS'; }]) {
    const f = fixture(); mutate(f); await assert.rejects(f.adapter.restart({ taskArn: arn }));
    assert.equal(f.calls.some(x => x.args[1] === 'stop-task'), false);
  }
});
test('AWS CLI isolates credentials, bounds invocation and rejects general commands', async () => {
  let invocation;
  const call = createAwsCli({ readProfile: 'reader', cliPath: 'aws.exe' }, target, async (...args) => { invocation = args; return { stdout: '{}' }; });
  await call(['sts', 'get-caller-identity']); assert.ok(invocation[1].includes('reader'));
  assert.equal(invocation[2].env.AWS_ACCESS_KEY_ID, undefined); assert.equal(invocation[2].windowsHide, true);
  await assert.rejects(call(['iam', 'create-user'])); await assert.rejects(call(['ecs', 'stop-task']));
});
test('local Docker failure does not prevent cloud observation', async () => {
  const f = fixture(); await f.adapter.refresh(true);
  const c = { ...config, targets: [target, { id: 'local', container: 'local', probe: 'container' }] };
  const sample = await observe(c, { snapshot: async () => ({ dockerOk: false, targets: { 'cloud-ebo': f.adapter.snapshot() } }) });
  assert.equal(sample.evidence.samples.find(x => x.target === 'cloud-ebo').status, 'healthy');
  assert.equal(sample.evidence.samples.find(x => x.target === 'local'), undefined);
  assert.equal(sample.status, 'healthy');
});
test('independent target incidents do not mask or close one another', async () => {
  const store = memory({}); const submitted = [];
  const c = { ...config, runtimeEnvironment: 'local', targets: [{ id: 'one' }, { id: 'two' }] };
  const control = new Controllers(store, c, { submit: async x => { submitted.push(x.target); return {}; }, job: async () => ({ status: 'running' }), cancel: async () => {}, notify: async () => {} });
  const samples = [{ target: 'one', status: 'fault', code: 'failed', evidence: {} }, { target: 'two', status: 'fault', code: 'failed', evidence: {} }];
  for (const at of [0, 60]) await control.tick({ evidence: { samples } }, at);
  assert.deepEqual(submitted.sort(), ['one', 'two']); assert.equal(store.value.incidents.length, 2);
  samples[0] = { target: 'one', status: 'healthy' };
  await control.tick({ evidence: { samples } }, 70); await control.tick({ evidence: { samples } }, 100);
  assert.equal(store.value.incidents.length, 1); assert.equal(store.value.incident.target, 'two');
});
test('monitoring permission failures notify without invoking a model', async () => {
  let models = 0; let alerts = 0;
  const control = new Controller(memory({}), config, { submit: async () => models++, notify: async () => alerts++ });
  for (const at of [0, 60, 300, 600]) await control.tick({ status: 'fault', target: target.id, code: 'aws_access_denied', diagnosticEligible: false }, at);
  assert.equal(models, 0); assert.equal(alerts, 1);
});
test('cached cloud readings cannot alone confirm a fault or sustained recovery', async () => {
  let models = 0; const store = memory({});
  const control = new Controller(store, config, { submit: async () => { models++; return {}; }, job: async () => ({ status: 'running' }), cancel: async () => {}, notify: async () => {} });
  const bad = { status: 'fault', target: target.id, code: 'stalled', evidence: { cloud: { observedAt: 1000 } } };
  await control.tick(bad, 1000); await control.tick(bad, 1060); assert.equal(models, 0);
  bad.evidence.cloud.observedAt = 1061; await control.tick(bad, 1061); assert.equal(models, 1);
  const good = { status: 'healthy', evidence: { cloud: { observedAt: 1070 } } };
  await control.tick(good, 1070); await control.tick(good, 1101); assert.ok(store.value.incident);
  good.evidence.cloud.observedAt = 1130; await control.tick(good, 1130); assert.equal(store.value.incident, null);
});
test('cloud bridge reserves one action despite concurrent replacement requests', async () => {
  let actions = 0; const t = { ...target, restartOnStall: true };
  const b = new ActionBridge(memory({ actions: {}, notifications: {} }), { ...config, targets: [t] }, {
    prepareRestart: async () => ({ taskArn: arn }), restart: async () => actions++ });
  await Promise.all(['a', 'b'].map(id => b.route('POST', '/restart', { id, target: t.id })));
  await new Promise(resolve => setImmediate(resolve)); assert.equal(actions, 1);
});

test('realistic AWS recovery timeline replaces once and avoids all model calls', async () => {
  let actions = 0; let models = 0; const store = memory({});
  const control = new Controller(store, config, { restart: async () => actions++, submit: async () => models++, notify: async () => {}, cancel: async () => {} });
  const bad = at => ({ status: 'fault', target: target.id, code: 'aws_video_stalled', recoverable: true,
    recoverySeconds: 300, evidence: { cloud: { observedAt: at } } });
  await control.tick(bad(1000), 1000); await control.tick(bad(1060), 1060);
  await control.tick({ status: 'grace', code: 'aws_scheduler_recovering' }, 1120);
  await control.tick({ status: 'healthy', evidence: { cloud: { observedAt: 1180 } } }, 1180);
  await control.tick({ status: 'healthy', evidence: { cloud: { observedAt: 1240 } } }, 1240);
  assert.equal(actions, 1); assert.equal(models, 0); assert.equal(store.value.incident, null);
});
test('replacement storm persists across adapter restart and skips another recovery', async () => {
  const f = fixture(); await f.adapter.refresh(true);
  for (const at of [1060, 1120, 1180]) { f.setAt(at); f.task.taskArn = arn + at; await f.adapter.refresh(true); }
  const restarted = new AwsEcsAdapter(f.adapter.target, config, f.connection, f.adapter.store, f.call, () => 1180);
  assert.equal(restarted.snapshot().observation.code, 'aws_task_replacement_storm');
  assert.equal(restarted.snapshot().observation.recoverable, false);
});
test('policies separate read and action permissions and scope logs and cluster', () => {
  const { read, action } = awsPolicies(target);
  assert.equal(read.Statement.some(s => s.Action.some(a => /Stop|Update|RunTask|iam:/.test(a))), false);
  assert.deepEqual(action.Statement.at(-1).Action, ['ecs:StopTask']);
  assert.equal(read.Statement.find(s => s.Sid === 'ConfiguredLogs').Resource.length, 2);
  assert.equal(read.Statement.find(s => s.Sid === 'ListClusterTasks').Condition.ArnEquals['ecs:cluster'], 'arn:aws:ecs:ca-central-1:123456789012:cluster/ebo-cloud-lab');
});
