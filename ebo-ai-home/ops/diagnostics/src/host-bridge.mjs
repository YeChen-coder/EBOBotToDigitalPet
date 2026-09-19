import path from 'node:path';
import fs from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { Store, readConfig, required, serve, now, sleep, audit } from './common.mjs';
import { ActionBridge, Guardian } from './bridge.mjs';
import { diagnosticEvents } from './telemetry.mjs';
import { AwsEcsAdapter } from './aws-ecs.mjs';
import { createAwsCli } from './aws-cli.mjs';
import { activeTargets } from './environment.mjs';
import { RuntimeControl } from './runtime.mjs';
import { createRuntimeIO } from './runtime-io.mjs';
import { serveDashboard } from './dashboard.mjs';
import { ConversationLog } from './conversations.mjs';
import { BillingMonitor } from './billing.mjs';

const exec = promisify(execFile);
const config = readConfig();
const data = process.env.HOST_DATA_DIR || './local/host';
const awsHostPath = process.env.AWS_HOST_CONFIG_PATH || './local/aws-host.json';
const awsHost = fs.existsSync(awsHostPath) ? JSON.parse(fs.readFileSync(awsHostPath, 'utf8').replace(/^\uFEFF/, '')) : { connections: {} };
const calls = new Map();
const adapters = new Map(config.targets.filter(t => t.adapter === 'aws-ecs').map(t => {
  const connection = { ...(awsHost.connections[t.aws.connection] || {}), allowRootReadOnce: false };
  const call = createAwsCli(connection, t); calls.set(t.id, call);
  return [t.id, new AwsEcsAdapter(t, config, connection,
    new Store(path.join(data, `aws-${t.id}.json`), {}), call)];
}));
const childEnv = () => { const env = { ...process.env }; delete env.OPENAI_ADMIN_KEY; return env; };
const docker = (args, timeout = 5000) => exec(process.env.DOCKER_BIN || 'docker', args, { env: childEnv(), timeout, windowsHide: true, maxBuffer: 128 * 1024 });
const runtimeIO = createRuntimeIO({ config, docker, adapters, calls, projectRoot: path.resolve('../..') });
const runtime = new RuntimeControl(new Store(path.join(data, 'runtime.json'), {}), config, runtimeIO);
let conversations;
try {
  conversations = new ConversationLog({ store: new Store(path.join(data, 'conversations.json'), {}),
    targets: config.targets.filter(t => t.adapter === 'aws-ecs'), calls, directory: path.resolve('../../assistant-data'), settings: config.conversationLogs });
} catch { audit('conversation_initialization_failed'); }
const billing = new BillingMonitor({ store: new Store(path.join(data, 'billing.json'), {}),
  awsCall: calls.values().next().value, openAIKey: process.env.OPENAI_ADMIN_KEY || '' });
async function dockerOk() { try { await docker(['info', '--format', '{{.ServerVersion}}']); return true; } catch { return false; } }
async function snapshot() {
  const ready = await dockerOk();
  const entries = await Promise.all(activeTargets(config).map(async t => {
    if (t.adapter === 'aws-ecs') return [t.id, adapters.get(t.id).snapshot()];
    if (!ready) return [t.id, { status: 'unavailable' }];
    try {
      const { stdout } = await docker(['inspect', '--format', '{"state":{{json .State}},"restartCount":{{.RestartCount}}}', t.container]);
      const inspected = JSON.parse(stdout); const state = inspected.state;
      return [t.id, { status: state.Status, exitCode: state.ExitCode, oomKilled: state.OOMKilled,
        ageSeconds: Math.max(0, now() - Date.parse(state.StartedAt) / 1000), health: state.Health?.Status || 'none', restartCount: inspected.restartCount }];
    } catch { return [t.id, { status: 'missing' }]; }
  }));
  return { runtimeEnvironment: config.runtimeEnvironment, runtime: runtime.status(), dockerOk: ready, targets: Object.fromEntries(entries), observedAt: now() };
}
async function localNotify(message) {
  fs.mkdirSync(data, { recursive: true });
  fs.appendFileSync(path.join(data, 'alerts.jsonl'), JSON.stringify({ at: new Date().toISOString(), message }) + '\n');
  if (process.platform !== 'win32') { audit('local_alert', { message }); return; }
  await exec('powershell.exe', ['-NoProfile', '-NonInteractive', '-File', path.resolve('scripts/notify-local.ps1')], {
    env: { ...childEnv(), EBO_DIAGNOSTIC_MESSAGE: message }, windowsHide: true, timeout: 15000,
  });
}
const bridge = new ActionBridge(new Store(path.join(data, 'actions.json'), { actions: {}, notifications: {} }), config,
  { snapshot, prepareRestart: t => adapters.get(t.id).prepareRestart(), actionsBlocked: () => runtime.busy || runtime.status().monitoringSuppressed,
    restart: (container, t, context) => runtime.repair(() => t.adapter === 'aws-ecs' ? adapters.get(t.id).restart(context) : docker(['restart', '--time', '20', container], 35000)), notify: localNotify,
    evidence: async (container, t) => {
      if (t.adapter === 'aws-ecs') return adapters.get(t.id).evidence();
      const { stdout, stderr } = await docker(['logs', '--since', '10m', '--tail', '200', '--timestamps', container], 6000);
      return { observedAt: now(), events: diagnosticEvents(stdout + '\n' + stderr), scope: 'last_200_lines_within_10m_categories_only' };
    },
  });
const guardian = new Guardian(new Store(path.join(data, 'guardian.json'), { outage: null }), config,
  { restartDocker: () => docker(['desktop', 'restart', '--detach'], 15000), notify: localNotify });
serve({ host: process.env.BRIDGE_HOST || '0.0.0.0', port: Number(process.env.BRIDGE_PORT || 8177), token: required('BRIDGE_TOKEN'),
  health: () => ({ ok: true, pid: process.pid, runtimeEnvironment: config.runtimeEnvironment, observationOnly: config.observationOnly, maintenance: config.maintenance }),
  route: (method, url, body) => {
    if (method === 'GET' && url === '/runtime') return runtime.status();
    if (method === 'POST' && url === '/runtime') return runtime.request(body.mode);
    if (method === 'POST' && url === '/restart' && (runtime.busy || runtime.status().monitoringSuppressed)) return { code: 409, body: { error: 'runtime_busy' } };
    return bridge.route(method, url, body);
  } });
serveDashboard({ runtime, reportDir: path.resolve('local/health-report'), config, awsHost, conversations, billing });
audit('host_bridge_started', { observationOnly: config.observationOnly, guardianAutoRestart: config.guardianAutoRestart });
let watcherBadSince = null; let watcherNotified = false; let nextRuntimePoll = 0;
while (true) {
  try {
    // Independent, bounded collection. Browser refreshes only read the local cache.
    if (conversations) void conversations.poll(config.runtimeEnvironment).catch(() => audit('conversation_collection_failed'));
    void billing.poll().catch(() => audit('billing_collection_failed'));
    if (now() >= nextRuntimePoll) { nextRuntimePoll = now() + 60; void runtime.poll().catch(() => audit('runtime_poll_failed')); }
    for (const t of activeTargets(config).filter(t => t.adapter === 'aws-ecs')) if (!runtime.busy && !config.maintenance && !t.maintenance) void adapters.get(t.id).refresh();
    const ready = await dockerOk();
    await guardian.tick(ready, now());
    // Covers monitoring-container failure without attempting to launch an AI.
    if (ready && !config.observationOnly && !config.maintenance) {
      let alive = false;
      try { const r = await fetch('http://127.0.0.1:8178/health', { signal: AbortSignal.timeout(4000) }); alive = (await r.json()).ok === true; } catch {}
      if (alive) { watcherBadSince = null; watcherNotified = false; }
      else {
        watcherBadSince ??= now();
        if (!watcherNotified && now() - watcherBadSince > config.notifySeconds) { await localNotify('EBO: Watcher 心跳持续异常，请检查诊断容器。'); watcherNotified = true; }
      }
    }
  } catch { audit('guardian_tick_failed'); }
  await sleep(config.pollSeconds * 1000);
}
