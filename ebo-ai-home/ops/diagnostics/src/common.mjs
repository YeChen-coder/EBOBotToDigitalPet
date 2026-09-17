import fs from 'node:fs';
import path from 'node:path';
import { timingSafeEqual } from 'node:crypto';
import http from 'node:http';
import { adapterName, validateAwsTarget } from './aws-config.mjs';
import { activeTargets } from './environment.mjs';

export const now = () => Date.now() / 1000;
export const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
export function required(name) {
  const value = process.env[name];
  if (!value || value.length < 24) throw new Error(`${name} must contain at least 24 characters`);
  return value;
}
export function readConfig() {
  const c = JSON.parse(fs.readFileSync(process.env.CONFIG_PATH || './config.local.json', 'utf8').replace(/^\uFEFF/, ''));
  for (const k of ['pollSeconds', 'confirmSeconds', 'startupSeconds', 'recoverySeconds', 'healthySeconds', 'notifySeconds', 'repeatWindowSeconds', 'diagnosisSeconds']) {
    if (!Number.isFinite(c[k]) || c[k] <= 0) throw new Error(`Invalid config: ${k}`);
  }
  if (!Array.isArray(c.targets) || !c.targets.length) throw new Error('Missing targets');
  const names = new Set();
  const resources = new Set();
  for (const t of c.targets) {
    if (!/^[a-z][a-z0-9-]+$/.test(t.id) || names.has(t.id)) throw new Error('Invalid/duplicate target');
    names.add(t.id);
    if (adapterName(t) === 'aws-ecs') {
      validateAwsTarget(t);
      const resource = [t.aws.accountId, t.aws.region, t.aws.cluster, t.aws.service].join('/');
      if (resources.has(resource)) throw new Error('Duplicate AWS service recovery unit');
      resources.add(resource);
    }
    else if (adapterName(t) !== 'docker' || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]+$/.test(t.container) || !['container', 'http', 'ebo-health'].includes(t.probe)) throw new Error('Invalid adapter/container/probe');
  }
  if (!activeTargets(c).length && c.runtimeEnvironment !== 'stopped') throw new Error('No enabled targets in selected runtimeEnvironment');
  return c;
}

// A single process owns each file. Corrupt state fails closed rather than erasing action budgets.
export class Store {
  constructor(file, initial) {
    this.file = file;
    fs.mkdirSync(path.dirname(file), { recursive: true });
    this.value = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : structuredClone(initial);
  }
  save() {
    const temp = this.file + '.tmp';
    const fd = fs.openSync(temp, 'w', 0o600);
    try { fs.writeFileSync(fd, JSON.stringify(this.value)); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    fs.renameSync(temp, this.file);
  }
}

export async function jsonFetch(url, { token, method = 'GET', body, timeout = 5000, signal } = {}) {
  const response = await fetch(url, {
    method, redirect: 'error',
    headers: { ...(token ? { authorization: `Bearer ${token}` } : {}), ...(body ? { 'content-type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(timeout)]) : AbortSignal.timeout(timeout),
  });
  // Bound response bytes even if upstream sends a misleading/missing Content-Length.
  const chunks = []; let size = 0;
  for await (const chunk of response.body) {
    size += chunk.length;
    if (size > 512 * 1024) throw new Error('response_too_large');
    chunks.push(chunk);
  }
  if (!response.ok) throw new Error(`http_${response.status}`);
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

export function validId(id) { return typeof id === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(id); }
export function failure(error) {
  // Never expose arbitrary SDK/provider exception text, URLs, tokens or subprocess output.
  const known = ['credentials_not_configured', 'invalid_diagnosis', 'provider_failed'];
  return { status: 'failed', error: ['TimeoutError', 'AbortError'].includes(error?.name) ? 'timeout' : known.includes(error?.message) ? error.message : 'execution_failed' };
}
export function serve({ port, host = '0.0.0.0', token, route, health = () => ({ ok: true }) }) {
  const server = http.createServer(async (req, res) => {
    const send = (status, data) => {
      res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      res.end(JSON.stringify(data));
    };
    try {
      if (req.url === '/health' && req.method === 'GET') return send(200, health());
      const a = Buffer.from(req.headers.authorization || ''); const b = Buffer.from(`Bearer ${token}`);
      if (a.length !== b.length || !timingSafeEqual(a, b)) return send(401, { error: 'unauthorized' });
      let text = ''; let bytes = 0;
      for await (const chunk of req) {
        bytes += chunk.length;
        if (bytes > 256 * 1024) { send(413, { error: 'body_too_large' }); return; }
        text += chunk;
      }
      let body;
      try { body = text ? JSON.parse(text) : {}; } catch { return send(400, { error: 'invalid_json' }); }
      const result = await route(req.method, req.url, body);
      send(result?.code || 200, result?.body ?? result);
    } catch { if (!res.headersSent) send(500, { error: 'request_failed' }); }
  });
  server.requestTimeout = 10000;
  server.headersTimeout = 10000;
  server.listen(port, host);
  return server;
}

export function audit(event, fields = {}) {
  console.log(JSON.stringify({ at: new Date().toISOString(), event, ...fields }));
}
