import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Store, jsonFetch, serve, sleep } from '../src/common.mjs';
import { Controller } from '../src/controller.mjs';
import { classifyHealth, healthEvidence, observe } from '../src/probes.mjs';
import { ActionBridge, Guardian } from '../src/bridge.mjs';
import { Jobs } from '../src/jobs.mjs';
import { remoteDiagnosis, validateDiagnosis } from '../src/providers.mjs';
import { notificationText } from '../src/notifications.mjs';
import { diagnosticEvents } from '../src/telemetry.mjs';

const config = { runtimeEnvironment: 'local', observationOnly: false, autoRecovery: true, maintenance: false,
  confirmSeconds: 10, recoverySeconds: 20, healthySeconds: 5, repeatWindowSeconds: 100,
  notifySeconds: 40, diagnosisSeconds: 30, startupSeconds: 45,
  targets: [{ id: 'assistant', container: 'ebo-ai-home-realtime-assistant', restartOnStall: true, probe: 'ebo-health', url: 'http://unused' }] };
const bad = { status: 'fault', code: 'video_stalled', target: 'assistant', recoverable: true, evidence: {} };
const good = { status: 'healthy', code: 'healthy', evidence: {} };
function makeStore(t, initial) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ebo-diag-test-'));
  t.after(() => {
    const resolved = path.resolve(dir);
    assert.equal(path.dirname(resolved), path.resolve(os.tmpdir()));
    assert.ok(path.basename(resolved).startsWith('ebo-diag-test-'));
    fs.rmSync(resolved, { recursive: true, force: true });
  });
  return new Store(path.join(dir, 'state.json'), initial);
}
function fixture(t, overrides = {}, ioOverrides = {}) {
  const calls = { restart: [], submit: [], notify: [], cancel: [] };
  const store = makeStore(t, { incident: null, recoveries: [], history: [] });
  const io = {
    restart: async (...args) => { calls.restart.push(args); return { status: 'accepted' }; },
    submit: async body => { calls.submit.push(body); return { status: 'queued' }; },
    job: async () => ({ status: 'running' }),
    cancel: async id => calls.cancel.push(id),
    notify: async (...args) => calls.notify.push(args), ...ioOverrides,
  };
  const c = { ...config, ...overrides };
  return { control: new Controller(store, c, io), calls, store, io, c };
}

test('bounded recovery succeeds: exactly one restart and zero model jobs', async t => {
  const f = fixture(t);
  for (const at of [0, 5, 10, 15]) await f.control.tick(bad, at);
  await f.control.tick(good, 20); await f.control.tick(good, 25);
  assert.equal(f.calls.restart.length, 1); assert.equal(f.calls.submit.length, 0);
  assert.equal(f.store.value.incident, null); assert.equal(f.calls.notify.length, 0);
});
test('failed recovery submits once, polls, and notifies independently of model progress', async t => {
  const f = fixture(t);
  for (const at of [0, 10, 20, 30, 40, 50, 100]) await f.control.tick(bad, at);
  assert.equal(f.calls.restart.length, 1); assert.equal(f.calls.submit.length, 1); assert.equal(f.calls.notify.length, 1);
  assert.ok(f.calls.submit[0].evidence.action);
});
test('model says normal but actual probe fails: incident stays unresolved', async t => {
  const f = fixture(t, { autoRecovery: false }, { job: async () => ({ status: 'completed', result: 'all healthy' }) });
  await f.control.tick(bad, 0); await f.control.tick(bad, 10);
  assert.equal(f.store.value.incident.phase, 'unresolved'); assert.equal(f.calls.notify.length, 1);
});
test('uncertain restart response is not retried after process restart', async t => {
  let restarts = 0;
  const f = fixture(t, {}, { restart: async () => { restarts++; throw new Error('connection_lost'); } });
  await f.control.tick(bad, 0); await f.control.tick(bad, 10);
  const loaded = new Store(f.store.file, {});
  const restarted = new Controller(loaded, f.c, f.io);
  await restarted.tick(bad, 20); await restarted.tick(bad, 30);
  assert.equal(restarts, 1); assert.equal(f.calls.submit.length, 1);
});
test('intermittent health resets pending confirmation', async t => {
  const f = fixture(t);
  await f.control.tick(bad, 0); await f.control.tick(good, 8); await f.control.tick(bad, 9); await f.control.tick(bad, 15);
  assert.equal(f.calls.restart.length, 0);
  await f.control.tick(bad, 19); assert.equal(f.calls.restart.length, 1);
});
test('recurrent failure skips another restart and escalates', async t => {
  const f = fixture(t);
  await f.control.tick(bad, 0); await f.control.tick(bad, 10); await f.control.tick(good, 20); await f.control.tick(good, 25);
  await f.control.tick(bad, 30); await f.control.tick(bad, 40);
  assert.equal(f.calls.restart.length, 1); assert.equal(f.calls.submit.length, 1);
});
test('observation-only performs no actions, model calls or notifications', async t => {
  const f = fixture(t, { observationOnly: true });
  for (const at of [0, 10, 100]) await f.control.tick(bad, at);
  assert.equal(f.calls.restart.length + f.calls.submit.length + f.calls.notify.length, 0);
});
test('notification failures retry with backoff; successful delivery deduplicates', async t => {
  let attempts = 0;
  const f = fixture(t, {}, { notify: async () => { if (++attempts === 1) throw new Error('offline'); } });
  for (const at of [0, 10, 40, 50, 70, 100]) await f.control.tick(bad, at);
  assert.equal(attempts, 2); assert.equal(f.store.value.incident.notified, true);
});
test('missing runbook goes directly to diagnosis without restart', async t => {
  const f = fixture(t);
  await f.control.tick({ ...bad, recoverable: false }, 0); await f.control.tick({ ...bad, recoverable: false }, 10);
  assert.equal(f.calls.restart.length, 0); assert.equal(f.calls.submit.length, 1);
});
test('muting during investigation cancels job and records suppression, not recovery', async t => {
  const f = fixture(t, { autoRecovery: false });
  await f.control.tick(bad, 0); await f.control.tick(bad, 10);
  await f.control.tick({ status: 'suppressed', code: 'muted' }, 12);
  assert.equal(f.calls.cancel.length, 1); assert.equal(f.store.value.closed[0].outcome, 'suppressed_not_verified');
});

const healthy = { ok: true, realtime_connected: true, video_streaming: true, audio_streaming: true, source_audio_status: 'receiving', source_audio_ok: true };
test('health distinguishes intentional mute, transport padding, and real source audio', () => {
  const t = config.targets[0];
  assert.equal(classifyHealth(healthy, t, config).status, 'healthy');
  assert.equal(classifyHealth({ ...healthy, ok: false, source_audio_status: 'muted' }, t, config).status, 'suppressed');
  const padded = classifyHealth({ ...healthy, ok: false, source_audio_status: 'no_source_packets', source_audio_ok: false }, t, config);
  assert.equal(padded.status, 'fault'); assert.equal(padded.recoverable, false);
  assert.equal(classifyHealth({ ok: true }, t, config).code, 'health_contract_invalid');
});
test('mute does not suppress broken video; it disables automatic restart', () => {
  const sample = classifyHealth({ ...healthy, source_audio_status: 'muted', video_streaming: false }, config.targets[0], config);
  assert.equal(sample.status, 'fault'); assert.equal(sample.recoverable, false);
});
test('health evidence omits free text, conversation data and credentials', () => {
  const e = healthEvidence({ ...healthy, last_error: 'token=secret', transcript: 'household conversation', source_audio_status: 'arbitrary text' });
  assert.equal(JSON.stringify(e).includes('secret'), false); assert.equal(e.source_audio_status, 'unknown');
});
test('exit 0 alone is a fault; explicit target maintenance suppresses the stop', async () => {
  const bridge = { snapshot: async () => ({ dockerOk: true, targets: { assistant: { status: 'exited', exitCode: 0 } } }) };
  assert.equal((await observe(config, bridge)).code, 'container_stopped_unexpected');
  assert.equal((await observe({ ...config, targets: config.targets.map(t => ({ ...t, maintenance: true })) }, bridge)).status, 'suppressed');
  bridge.snapshot = async () => ({ dockerOk: false });
  assert.equal((await observe(config, bridge)).code, 'docker_unavailable');
});

test('explicit Docker pause suppresses diagnosis and unpause resumes normal probing', async () => {
  let paused = true;
  const bridge = { snapshot: async () => ({ dockerOk: true, targets: { assistant: { status: paused ? 'paused' : 'running', ageSeconds: 1000 } } }) };
  assert.equal((await observe(config, bridge)).evidence.samples[0].code, 'container_paused');
  paused = false;
  assert.equal((await observe(config, bridge, async () => healthy)).status, 'healthy');
});

test('bridge rejects arbitrary targets, cooldown bypass, and replayed operations', async t => {
  const store = makeStore(t, { actions: {}, notifications: {} }); let restarts = 0;
  const b = new ActionBridge(store, config, { snapshot: async () => ({ dockerOk: true, targets: { assistant: { status: 'running' } } }), restart: async () => restarts++ });
  assert.equal((await b.route('POST', '/restart', { id: 'a', target: 'anything' })).code, 403);
  await b.route('POST', '/restart', { id: 'a', target: 'assistant' });
  await b.route('POST', '/restart', { id: 'a', target: 'assistant' });
  assert.equal((await b.route('POST', '/restart', { id: 'b', target: 'assistant' })).code, 409);
  await sleep(5); assert.equal(restarts, 1);
});
test('concurrent bridge requests reserve a target only once', async t => {
  const store = makeStore(t, { actions: {}, notifications: {} }); let restarts = 0;
  const b = new ActionBridge(store, config, { snapshot: async () => { await sleep(5); return { dockerOk: true, targets: { assistant: { status: 'running' } } }; }, restart: async () => restarts++ });
  await Promise.all(['a', 'b'].map(id => b.route('POST', '/restart', { id, target: 'assistant' })));
  await sleep(5); assert.equal(restarts, 1);
});
test('guardian attempts Docker restart only once, then notifies without a model', async t => {
  const store = makeStore(t, { outage: null }); let restarts = 0; let notices = 0;
  const g = new Guardian(store, { ...config, guardianAutoRestart: true }, { restartDocker: async () => restarts++, notify: async () => notices++ });
  for (const at of [0, 10, 20, 40, 80]) await g.tick(false, at);
  assert.equal(restarts, 1); assert.equal(notices, 1);
});

test('job protocol idempotency and cancellation stop a running provider', async t => {
  let runs = 0;
  const store = makeStore(t, { jobs: {} });
  const jobs = new Jobs(store, async (_, signal) => { runs++; await new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new Error('abort')), { once: true })); });
  const request = { id: 'incident-a', schemaVersion: 1, evidence: {}, timeoutSeconds: 30 };
  await jobs.route('POST', '/jobs', request); await sleep(5); await jobs.route('POST', '/jobs', request);
  await jobs.route('POST', '/jobs/incident-a/cancel', {}); await sleep(5);
  assert.equal(runs, 1); assert.equal(store.value.jobs['incident-a'].status, 'cancelled');
});
test('interrupted paid job is failed on worker restart, never replayed', async t => {
  let runs = 0;
  const store = makeStore(t, { jobs: { a: { id: 'a', status: 'running', request: {} } } });
  new Jobs(store, async () => runs++); await sleep(5);
  assert.equal(runs, 0); assert.equal(store.value.jobs.a.error, 'worker_restarted');
});
test('provider deadline aborts work and releases concurrency slot', async t => {
  const store = makeStore(t, { jobs: {} });
  const jobs = new Jobs(store, async (_, signal) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new Error('deadline')))), { maxSeconds: 0.02 });
  await jobs.route('POST', '/jobs', { id: 'deadline', schemaVersion: 1, evidence: {}, timeoutSeconds: 1 });
  await sleep(60); assert.equal(store.value.jobs.deadline.error, 'timeout'); assert.equal(jobs.active, null);
});
test('remote provider is replaceable and cancellation is forwarded after failure', async () => {
  const calls = [];
  const transport = async (url, args) => { calls.push(url); if (url.endsWith('/cancel')) return {}; throw new Error('network'); };
  await assert.rejects(remoteDiagnosis({ id: 'x' }, new AbortController().signal, { url: 'http://other-worker', token: 'secret' }, transport));
  assert.equal(calls.at(-1), 'http://other-worker/jobs/x/cancel');
});
test('API server enforces authentication and body size', async t => {
  const server = serve({ port: 0, host: '127.0.0.1', token: 'a'.repeat(32), route: async () => ({ accepted: true }) });
  await new Promise(resolve => server.on('listening', resolve));
  t.after(() => { server.closeAllConnections(); server.close(); });
  const url = `http://127.0.0.1:${server.address().port}`;
  assert.equal((await fetch(url + '/jobs')).status, 401);
  assert.equal((await jsonFetch(url + '/jobs', { token: 'a'.repeat(32), method: 'POST', body: {} })).accepted, true);
  assert.equal((await fetch(url + '/jobs', { method: 'POST', headers: { authorization: `Bearer ${'a'.repeat(32)}` }, body: 'x'.repeat(270000) })).status, 413);
});
test('notification excludes untrusted model output', () => {
  assert.equal(notificationText({ id: 'a', job: { result: 'secret transcript' } }, 'unresolved').includes('transcript'), false);
});
test('malformed model output is rejected', () => {
  assert.throws(() => validateDiagnosis({ assessment: 'healthy' }));
});
test('log collector exports only event categories, never raw lines', () => {
  const out = diagnosticEvents('2026-09-10T01:00:00.000Z TimeoutError token=SECRET household transcript\nother text');
  assert.deepEqual(out, [{ at: '2026-09-10T01:00:00.000Z', event: 'timeout' }]);
});
test('restarts during startup are detected from increasing Docker restart count', async t => {
  const f = fixture(t);
  const sample = count => ({ status: 'grace', code: 'starting', evidence: { samples: [{ target: 'assistant', evidence: { container: { restartCount: count } } }] } });
  await f.control.tick(sample(10), 0); await f.control.tick(sample(13), 10); await f.control.tick(sample(14), 20);
  assert.equal(f.calls.restart.length, 0); assert.equal(f.calls.submit.length, 1);
  assert.equal(f.store.value.incident.code, 'container_restart_storm');
});
