import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { Controller } from '../src/controller.mjs';
import { ActionBridge } from '../src/bridge.mjs';
import { Store, jsonFetch, sleep } from '../src/common.mjs';
import { classifyHealth } from '../src/probes.mjs';

const exec = promisify(execFile);
const docker = (...args) => exec('docker', args, { timeout: 45000, windowsHide: true });
const results = [];
for (const persistent of [false, true]) {
  const name = `ebo-diag-fixture-${randomUUID().slice(0, 8)}`;
  const stateDir = path.resolve('local', name); fs.mkdirSync(stateDir, { recursive: true });
  let modelCalls = 0; let actionCalls = 0;
  try {
    await docker('run', '-d', '--name', name, '--label', 'ebo.diagnostics.test=true', '-p', '127.0.0.1::8188',
      '--mount', `type=bind,source=${path.resolve('test')},target=/fixtures,readonly`,
      '-e', `PERSISTENT_FAILURE=${persistent}`, 'ebo-diagnostics/watcher:0.1.0', 'node', '/fixtures/fixture.mjs');
    const { stdout } = await docker('port', name, '8188'); let url = `http://${stdout.trim()}`;
    for (let n = 0; n < 30; n++) { try { await jsonFetch(url); break; } catch { await sleep(200); } }
    await jsonFetch(url + '/break', { method: 'POST' });
    const config = { runtimeEnvironment: 'local', confirmSeconds: 1, recoverySeconds: 1, healthySeconds: 1, repeatWindowSeconds: 100,
      notifySeconds: 100, diagnosisSeconds: 10, autoRecovery: true, observationOnly: false, startupSeconds: 1,
      targets: [{ id: 'fixture', container: name, restartOnStall: true }] };
    const bridge = new ActionBridge(new Store(path.join(stateDir, 'bridge.json'), { actions: {}, notifications: {} }), config, {
      snapshot: async () => ({ dockerOk: true, targets: { fixture: { status: 'running' } } }),
      restart: async container => { assert.equal(container, name); actionCalls++; await docker('restart', '--time', '1', container); },
    });
    const store = new Store(path.join(stateDir, 'watcher.json'), { incident: null, recoveries: [], history: [] });
    const control = new Controller(store, config, {
      restart: async (target, id) => bridge.route('POST', '/restart', { target, id }),
      submit: async () => { modelCalls++; return { status: 'queued' }; }, job: async () => ({ status: 'running' }),
      notify: async () => {}, cancel: async () => {},
    });
    const sample = () => jsonFetch(url).then(h => classifyHealth(h, config.targets[0], config));
    await control.tick(await sample(), 0); await control.tick(await sample(), 1);
    for (let n = 0; n < 60; n++) {
      const action = Object.values(bridge.store.value.actions)[0];
      if (action.status === 'completed') break;
      await sleep(100);
    }
    assert.equal(Object.values(bridge.store.value.actions)[0].status, 'completed');
    url = `http://${(await docker('port', name, '8188')).stdout.trim()}`;
    for (let n = 0; n < 50; n++) { try { await sample(); break; } catch { await sleep(200); } }
    await control.tick(await sample(), 3); await control.tick(await sample(), 5);
    assert.equal(actionCalls, 1); assert.equal(modelCalls, persistent ? 1 : 0);
    if (!persistent) assert.equal(store.value.incident, null);
    results.push({ persistent, actualDockerRestarts: actionCalls, modelCalls, passed: true });
  } finally {
    // Exact container created by this test; never operate on the EBO application project.
    await docker('rm', '-f', name).catch(() => {});
  }
}
console.log(JSON.stringify(results, null, 2));
