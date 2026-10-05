import path from 'node:path';
import { now, sleep } from './common.mjs';
import { classifyHealth } from './probes.mjs';

const names = ['homeassistant', 'ebo-engine', 'realtime-assistant'];
const stopped = s => ['exited', 'created', 'dead', 'missing'].includes(s);

export function createRuntimeIO({ config, docker, adapters, calls, projectRoot, clock = now, pause = sleep }) {
  const locals = config.targets.filter(t => !t.adapter || t.adapter === 'docker');
  const clouds = config.targets.filter(t => t.adapter === 'aws-ecs');
  const compose = ['compose', '--project-directory', path.resolve(projectRoot), '-f', path.resolve(projectRoot, 'compose.yaml'), '--profile', 'assistant'];
  async function localState() {
    try { await docker(['info', '--format', '{{.ServerVersion}}']); } catch { return { known: false, stopped: null, error: 'docker_unavailable', containers: [] }; }
    const containers = [];
    for (const t of locals) {
      try {
        const { stdout } = await docker(['inspect', '--format', '{{json .State}}', t.container]);
        const s = JSON.parse(stdout);
        containers.push({ id: t.id, name: t.container, status: s.Status, health: s.Health?.Status || 'none' });
      } catch (e) {
        if (/No such (object|container)/i.test(String(e.stderr))) containers.push({ id: t.id, name: t.container, status: 'missing' });
        else return { known: false, stopped: null, error: 'docker_unavailable', containers };
      }
    }
    return { known: true, stopped: containers.every(c => stopped(c.status)), containers };
  }
  async function cloudState(t, control = false) {
    const call = calls.get(t.id); const a = t.aws; const options = { control };
    const id = await call(['sts', 'get-caller-identity'], options);
    if (id.Account !== a.accountId) throw new Error('aws_account_mismatch');
    if (!id.Arn || id.Arn.endsWith(':root')) throw new Error('aws_root_identity_refused');
    const r = await call(['ecs', 'describe-services', '--cluster', a.cluster, '--services', a.service], options);
    const s = r.services?.[0];
    if (r.failures?.length || !s || s.serviceName !== a.service || s.status !== 'ACTIVE') throw new Error('aws_service_missing');
    if (s.launchType !== 'FARGATE' && !(s.capacityProviderStrategy?.length && s.capacityProviderStrategy.every(p => ['FARGATE', 'FARGATE_SPOT'].includes(p.capacityProvider)))) throw new Error('aws_not_fargate');
    const arns = new Set();
    // Include tasks whose desired status is STOPPED but which are still STOPPING/DEPROVISIONING.
    for (const desired of ['RUNNING', 'STOPPED']) {
      const list = await call(['ecs', 'list-tasks', '--cluster', a.cluster, '--service-name', a.service, '--desired-status', desired, '--max-results', '100', '--no-paginate'], options);
      if (list.nextToken) throw new Error('aws_task_limit_exceeded');
      for (const arn of list.taskArns || []) arns.add(arn);
    }
    const all = [...arns]; const tasks = [];
    for (let offset = 0; offset < all.length; offset += 100) {
      const r = await call(['ecs', 'describe-tasks', '--cluster', a.cluster, '--tasks', ...all.slice(offset, offset + 100)], options);
      if (r.failures?.length) throw new Error('aws_task_snapshot_incomplete');
      tasks.push(...r.tasks || []);
    }
    const live = tasks.filter(t => t.lastStatus !== 'STOPPED');
    return { id: t.id, known: true, desiredCount: s.desiredCount, runningCount: s.runningCount, pendingCount: s.pendingCount,
      stopped: s.desiredCount === 0 && s.runningCount === 0 && s.pendingCount === 0 && live.length === 0,
      tasks: live.map(t => ({ id: t.taskArn.split('/').at(-1), status: t.lastStatus, health: t.healthStatus || 'UNKNOWN' })) };
  }
  async function autoscaling(t) {
    const a = t.aws;
    const r = await calls.get(t.id)(['application-autoscaling', 'describe-scalable-targets', '--service-namespace', 'ecs',
      '--resource-ids', `service/${a.cluster}/${a.service}`, '--scalable-dimension', 'ecs:service:DesiredCount'], { control: true });
    if (r.ScalableTargets?.some(t => !t.SuspendedState?.DynamicScalingInSuspended || !t.SuspendedState?.DynamicScalingOutSuspended || !t.SuspendedState?.ScheduledScalingSuspended)) throw new Error('aws_autoscaling_enabled');
  }
  async function until(check, error, seconds = 360) {
    const end = clock() + seconds;
    do { if (await check()) return; await pause(5000); } while (clock() < end);
    throw new Error(error);
  }
  const io = {
    async inspect() {
      const local = await localState();
      const services = await Promise.all(clouds.map(async t => {
        try { return await cloudState(t); } catch (e) { return { id: t.id, known: false, stopped: null, error: /^aws_[a-z_]+$/.test(e.message) ? e.message : 'aws_collection_failed' }; }
      }));
      const known = services.every(s => s.known);
      return { observedAt: clock(), local, cloud: { known, stopped: known ? services.every(s => s.stopped) : null, services } };
    },
    async stopLocal() {
      const state = await localState();
      if (!state.known) throw new Error('docker_unavailable');
      const failures = [];
      for (const c of state.containers.filter(c => c.status !== 'missing')) {
        try {
          await docker(['update', '--restart=no', c.name]);
          if (c.status === 'paused') await docker(['unpause', c.name]);
          if (!stopped(c.status)) await docker(['stop', '--time', '20', c.name], 35000);
        } catch (e) { failures.push(e); }
      }
      if (failures.length || !(await localState()).stopped) throw new Error('local_stop_unverified');
    },
    async stopCloud() {
      const failures = [];
      for (const t of clouds) {
        try {
          // Permission + autoscaling preflight happens even when already scaled to zero.
          await cloudState(t, true); await autoscaling(t);
          const a = t.aws;
          await calls.get(t.id)(['ecs', 'update-service', '--cluster', a.cluster, '--service', a.service, '--desired-count', '0'], { control: true });
          await until(async () => (await cloudState(t)).stopped, 'aws_stop_unverified');
        } catch (e) { failures.push(e); }
      }
      if (failures.length) throw failures[0];
    },
    async startCloud() {
      if (!clouds.length || clouds.some(t => t.enabled === false)) throw new Error('aws_service_missing');
      if (!(await localState()).stopped) throw new Error('local_stop_unverified');
      for (const t of clouds) {
        await cloudState(t, true); await autoscaling(t);
        const a = t.aws;
        await calls.get(t.id)(['ecs', 'update-service', '--cluster', a.cluster, '--service', a.service, '--desired-count', '1'], { control: true });
      }
    },
    async startLocal() {
      for (const t of clouds) if (!(await cloudState(t)).stopped) throw new Error('aws_stop_unverified');
      if (locals.length !== 3 || locals.some(t => t.enabled === false)) throw new Error('runtime_operation_failed');
      const before = await localState();
      for (const c of before.containers.filter(c => c.status === 'paused')) await docker(['unpause', c.name]);
      await docker([...compose, 'up', '-d', '--no-build', ...names], 180000);
      for (const t of locals) await docker(['update', '--restart=unless-stopped', t.container]);
    },
    async waitHealthy(mode, onSample = () => {}) {
      await until(async () => {
        if (mode === 'aws') {
          await Promise.all(clouds.map(t => adapters.get(t.id).refresh(true)));
          const checks = clouds.map(t => { const o = adapters.get(t.id).snapshot().observation; return { target: t.id, status: o.status, code: o.code, at: clock() }; });
          onSample(checks);
          return checks.every(c => c.status === 'healthy');
        }
        const local = await localState();
        onSample(local.containers.map(c => ({target:c.id,status:c.status === 'running' && c.health !== 'unhealthy' ? 'grace' : 'fault',code:c.status === 'running' ? 'starting' : 'container_not_running',at:clock()})));
        if (!local.known || local.containers.some(c => c.status !== 'running' || c.health === 'unhealthy')) return false;
        for (const t of locals) {
          if (t.probe === 'container') continue;
          try {
            const url = new URL(t.url); if (url.hostname === 'host.docker.internal') url.hostname = '127.0.0.1';
            const r = await fetch(url, { signal: AbortSignal.timeout(4000), redirect: 'manual' });
            if (t.probe === 'http') { await r.body?.cancel(); if (r.status < 200 || r.status >= 400) return false; }
            else { const o = classifyHealth(await r.json(), t, config); if(o.status !== 'healthy') { onSample([{target:t.id,status:o.status,code:o.code,at:clock()}]); return false; } }
          } catch { return false; }
        }
        return true;
      }, 'runtime_health_timeout');
    },
    matches(mode, actual) {
      if (!actual?.local.known || !actual.cloud.known) return false;
      if (mode === 'stopped') return actual.local.stopped && actual.cloud.stopped;
      if (mode === 'local') return actual.cloud.stopped && actual.local.containers.length === 3 && actual.local.containers.every(c => c.status === 'running');
      return actual.local.stopped && actual.cloud.services.length > 0 && actual.cloud.services.every(s => s.desiredCount === 1 && s.runningCount === 1 && s.pendingCount === 0 && s.tasks.length === 1 && s.tasks[0].status === 'RUNNING');
    },
  };
  return io;
}
