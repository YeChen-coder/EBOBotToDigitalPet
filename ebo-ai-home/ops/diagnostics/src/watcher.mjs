import path from 'node:path';
import { Store, required, readConfig, jsonFetch, serve, now, sleep, audit } from './common.mjs';
import { observe } from './probes.mjs';
import { Controllers } from './controllers.mjs';
import { notify } from './notifications.mjs';

const config = readConfig();
const bridgeToken = required('BRIDGE_TOKEN');
const diagToken = required('DIAGNOSTIC_TOKEN');
const bridgeUrl = process.env.BRIDGE_URL;
const diagUrl = process.env.DIAGNOSTIC_URL;
const bridge = {
  snapshot: () => jsonFetch(`${bridgeUrl}/snapshot`, { token: bridgeToken, timeout: 15000 }),
  restart: (target, id) => jsonFetch(`${bridgeUrl}/restart`, { token: bridgeToken, method: 'POST', body: { target, id }, timeout: 50000 }),
  notify: body => jsonFetch(`${bridgeUrl}/notify`, { token: bridgeToken, method: 'POST', body, timeout: 15000 }),
};
const store = new Store(path.join(process.env.DATA_DIR || './data/watcher', 'state.json'), { incident: null, recoveries: [], history: [] });
const control = new Controllers(store, config, {
  evidence: target => jsonFetch(`${bridgeUrl}/evidence`, { token: bridgeToken, method: 'POST', body: { target }, timeout: 50000 }),
  restart: bridge.restart,
  submit: body => jsonFetch(`${diagUrl}/jobs`, { token: diagToken, method: 'POST', body }),
  job: id => jsonFetch(`${diagUrl}/jobs/${id}`, { token: diagToken }),
  cancel: id => jsonFetch(`${diagUrl}/jobs/${id}/cancel`, { token: diagToken, method: 'POST' }),
  notify: (i, kind) => notify(i, kind, bridge),
});
let lastSuccessfulTick = 0;
serve({ port: Number(process.env.PORT || 8080), token: diagToken,
  health: () => ({ ok: now() - lastSuccessfulTick < config.pollSeconds * 3 + 120, runtimeEnvironment: config.runtimeEnvironment, mode: config.observationOnly ? 'observe' : 'active' }),
  route: async (method, url) => method === 'GET' && url === '/state' ? store.value : { code: 404, body: { error: 'not_found' } },
});
audit('watcher_started', { observationOnly: config.observationOnly });
while (true) {
  try { await control.tick(await observe(config, bridge), now()); lastSuccessfulTick = now(); }
  catch { audit('watcher_tick_failed'); }
  await sleep(config.pollSeconds * 1000);
}
