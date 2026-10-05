import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { activeTargets } from '../src/environment.mjs';
import { observe } from '../src/probes.mjs';
import { ActionBridge } from '../src/bridge.mjs';
import { Controllers } from '../src/controllers.mjs';

const local = JSON.parse(fs.readFileSync(new URL('../config.example.json', import.meta.url)));
const cloud = JSON.parse(fs.readFileSync(new URL('../aws-target.example.json', import.meta.url)));
const config = { ...local, observationOnly: false, targets: [...local.targets, cloud] };
const memory = (value = {}) => ({ value, save() {} });

test('explicit environment selects exactly three local containers OR the AWS service', () => {
  assert.deepEqual(activeTargets(config).map(t => t.id), ['engine', 'assistant', 'homeassistant']);
  assert.deepEqual(activeTargets({ ...config, runtimeEnvironment: 'aws' }).map(t => t.id), ['cloud-ebo']);
  for (const environment of [undefined, 'both', 'auto', 'cloud', 'AWS'])
    assert.throws(() => activeTargets({ ...config, runtimeEnvironment: environment }));
});

test('cloud health ignores all local business containers including paused HA', async () => {
  const sample = await observe({ ...config, runtimeEnvironment: 'aws' }, { snapshot: async () => ({
    dockerOk: true, targets: { engine: { status: 'exited' }, assistant: { status: 'missing' }, homeassistant: { status: 'paused' },
      'cloud-ebo': { observation: { status: 'healthy', code: 'aws_business_healthy' } } },
  }) }, async () => assert.fail('No local health endpoint should be called'));
  assert.equal(sample.status, 'healthy'); assert.equal(sample.evidence.samples.length, 1);
});

test('local health requires every selected container, and ignores absent AWS evidence', async () => {
  // Process probes isolate dependency selection; production HA and Assistant retain their HTTP contracts.
  const c = { ...config, targets: config.targets.map(t => t.adapter ? t : { ...t, probe: 'container' }) };
  const states = Object.fromEntries(local.targets.map(t => [t.id, { status: 'running', ageSeconds: 1000, health: 'healthy' }]));
  const bridge = { snapshot: async () => ({ dockerOk: true, targets: states }) };
  assert.equal((await observe(c, bridge)).status, 'healthy');
  for (const target of local.targets) {
    states[target.id].health = 'unhealthy';
    const sample = await observe(c, bridge);
    assert.equal(sample.status, 'fault'); assert.equal(sample.target, target.id);
    states[target.id].health = 'healthy';
  }
  states.homeassistant.status = 'paused';
  assert.equal((await observe(c, bridge)).status, 'suppressed');
});

test('inactive environment cannot request evidence or restart via the host bridge', async () => {
  for (const environment of ['local', 'aws']) {
    const c = { ...config, runtimeEnvironment: environment };
    const bridge = new ActionBridge(memory({ actions: {}, notifications: {} }), c, {
      evidence: async () => assert.fail('Inactive evidence call'), restart: async () => assert.fail('Inactive restart'),
    });
    for (const target of config.targets.filter(t => !activeTargets(c).includes(t))) {
      assert.equal((await bridge.route('POST', '/evidence', { target: target.id })).code, 403);
      assert.equal((await bridge.route('POST', '/restart', { id: 'a', target: target.id })).code, 403);
    }
  }
});

test('switching environment cancels old diagnosis and preserves its action budget', async () => {
  const cancelled = [];
  const store = memory({ scopes: { assistant: { incident: { id: 'old', target: 'assistant', jobSubmitted: true },
    recoveries: [{ target: 'assistant', at: 90 }], history: [] } } });
  const control = new Controllers(store, { ...config, runtimeEnvironment: 'aws' }, {
    cancel: async id => cancelled.push(id), submit: async () => assert.fail('No new model job'),
  });
  await control.tick({ status: 'healthy', evidence: { samples: [{ target: 'cloud-ebo', status: 'healthy' },
    { target: 'assistant', status: 'fault' }] } }, 100);
  assert.deepEqual(cancelled, ['old']); assert.equal(store.value.incidents.length, 0);
  assert.equal(store.value.scopes.assistant.closed[0].outcome, 'suppressed_not_verified');
  assert.equal(store.value.scopes.assistant.recoveries.length, 1);
  assert.deepEqual(store.value.excludedTargets, ['engine', 'assistant', 'homeassistant']);
});

test('mixed host and Watcher configurations fail as monitoring error without diagnosis', async () => {
  const sample = await observe(config, { snapshot: async () => ({ runtimeEnvironment: 'aws' }) });
  assert.equal(sample.code, 'runtime_environment_mismatch'); assert.equal(sample.diagnosticEligible, false);
  const store = memory();
  await new Controllers(store, { ...config, runtimeEnvironment: 'aws' }, {}).tick(sample, 0);
  assert.deepEqual(store.value.incidents.map(i => i.target), ['cloud-ebo']);
});

test('configuration commands validate before writing and keep sampling freshness consistent', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ebo-diag-env-'));
  t.after(() => {
    assert.equal(path.dirname(path.resolve(dir)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(dir).startsWith('ebo-diag-env-'));
    fs.rmSync(dir, { recursive: true });
  });
  const file = path.join(dir, 'config.json'); fs.writeFileSync(file, JSON.stringify(config));
  const run = (...args) => execFileSync(process.execPath, ['scripts/configure.mjs', ...args], {
    cwd: new URL('..', import.meta.url), env: { ...process.env, CONFIG_PATH: file }, stdio: 'pipe', windowsHide: true,
  });
  run('environment', 'aws'); run('sampling', '120');
  const updated = JSON.parse(fs.readFileSync(file));
  assert.equal(updated.runtimeEnvironment, 'aws'); assert.equal(updated.targets.at(-1).aws.pollSeconds, 120);
  assert.ok(updated.targets.at(-1).aws.snapshotMaxAgeSeconds >= 240);
  for (const args of [['environment', 'both'], ['sampling', '0'], ['sampling', '30.5']]) {
    assert.throws(() => run(...args)); assert.deepEqual(JSON.parse(fs.readFileSync(file)), updated);
  }
  fs.writeFileSync(file, JSON.stringify(local));
  assert.throws(() => run('environment', 'aws')); assert.deepEqual(JSON.parse(fs.readFileSync(file)), local);
});
