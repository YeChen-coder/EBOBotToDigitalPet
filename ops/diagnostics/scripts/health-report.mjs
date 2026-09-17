import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { jsonFetch, readConfig } from '../src/common.mjs';
import { assessHealth, incidentRows, renderReport } from '../src/health-report.mjs';

process.chdir(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'));
const dir = path.resolve('local/health-report');
fs.mkdirSync(dir, { recursive: true });
const exec = promisify(execFile);
const read = (file, fallback) => fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : fallback;
const save = (name, data) => { const dest = path.join(dir, name); fs.writeFileSync(dest + '.tmp', typeof data === 'string' ? data : JSON.stringify(data, null, 2)); fs.renameSync(dest + '.tmp', dest); };
async function docker(args) { return (await exec('docker', args, { windowsHide: true, timeout: 25000, maxBuffer: 12 * 1024 * 1024 })).stdout; }
const services = ['watcher', 'diagnostic-service', 'codex-triage', 'codex-worker'];
async function collect() {
  const config = readConfig();
  const data = { generatedAt: new Date().toISOString(), providers: {}, errors: [], maxAges: Object.fromEntries(config.targets.filter(t => t.aws).map(t => [t.id, t.aws.snapshotMaxAgeSeconds])) };
  const checks = [
    ['state', () => jsonFetch('http://127.0.0.1:8178/state', { token: process.env.DIAGNOSTIC_TOKEN })],
    ['watcher', () => jsonFetch('http://127.0.0.1:8178/health')],
    ['bridge', () => jsonFetch('http://127.0.0.1:8177/health')],
    ['containers', null],
    ['runtime', () => jsonFetch('http://127.0.0.1:8177/runtime', { token: process.env.BRIDGE_TOKEN })],
  ];
  // Inspect selects only state fields; environment variables (tokens) never leave Docker.
  checks[3][1] = async () => (await docker(['inspect', '--format', '{{json .Name}}|{{json .State.Status}}|{{json .State.Health.Status}}|{{json .State.StartedAt}}|{{json .RestartCount}}', ...services.map(s => `ebo-diagnostics-${s}-1`)])).trim().split(/\r?\n/).map(line => {
    const [name, status, health, startedAt, restartCount] = line.split('|').map(x => JSON.parse(x));
    return { service: name.replace('/ebo-diagnostics-', '').replace(/-1$/, ''), status, health, startedAt, restartCount };
  });
  for (const service of services.slice(1)) checks.push([service, async () => {
    // Read every retained job (the public list is limited to 30). Omit request evidence.
    const code = `const fs=require('fs');(async()=>{const health=await(await fetch('http://127.0.0.1:${service === 'diagnostic-service' ? 8081 : 8082}/health')).json();const jobs=Object.values(JSON.parse(fs.readFileSync('/data/jobs.json')).jobs).map(j=>({id:j.id,status:j.status,createdAt:j.createdAt,startedAt:j.startedAt,endedAt:j.endedAt,target:j.request?.target,symptom:j.request?.symptom,timeoutSeconds:j.request?.timeoutSeconds,result:j.result,error:j.error}));console.log(JSON.stringify({health,jobs}));})().catch(()=>process.exit(1));`;
    return JSON.parse(await docker(['compose', 'exec', '-T', service, 'node', '-e', code]));
  }]);
  const results = await Promise.allSettled(checks.map(([, fn]) => fn()));
  for (let n = 0; n < results.length; n++) {
    const r = results[n], name = checks[n][0];
    if (r.status === 'fulfilled') { if (services.slice(1).includes(name)) data.providers[name] = r.value; else data[name] = r.value; }
    else data.errors.push({ component: name, error: 'read_failed' });
  }
  data.assessment = assessHealth(data);
  const jobArchive = read(path.join(dir, 'jobs-history.json'), {});
  for (const service of services.slice(1)) {
    const merged = new Map((jobArchive[service] || []).map(j => [j.id, j]));
    for (const j of data.providers[service]?.jobs || []) merged.set(j.id, j);
    jobArchive[service] = [...merged.values()];
    data.providers[service] = { ...data.providers[service], jobs: jobArchive[service] };
  }
  save('jobs-history.json', jobArchive);
  data.incidents = incidentRows(data.state, data.providers, read(path.join(dir, 'incidents.json'), {}));
  data.cloudDay = read(path.join(dir, 'cloud-day.json'), null);
  data.guardian = read('local/host/guardian.json', null);
  // Latest state remains small; raw rolling observations stay in the Watcher volume.
  if (data.state) data.state = { runtimeEnvironment: data.state.runtimeEnvironment, lastTick: data.state.lastTick,
    activeTargets: data.state.activeTargets, excludedTargets: data.state.excludedTargets,
    lastSample: data.state.lastSample, incidents: data.state.incidents?.map(i => ({ id: i.id, target: i.target, phase: i.phase, code: i.code })) };
  save('incidents.json', data.incidents);
  save('latest.json', data);
  save('index.html', renderReport(data));
  fs.appendFileSync(path.join(dir, `samples-${data.generatedAt.slice(0, 10)}.jsonl`), JSON.stringify({ at: data.generatedAt, assessment: data.assessment, lastTick: data.state?.lastTick,
    targets: data.state?.lastSample?.evidence?.samples?.map(s => ({ target: s.target, status: s.status, code: s.code, cloudObservedAt: s.evidence?.cloud?.observedAt, taskIds: s.evidence?.cloud?.tasks?.map(t => t.taskArn.split('/').at(-1)) })),
    incidents: data.state?.incidents, errors: data.errors }) + '\n');
  console.log(JSON.stringify({ generatedAt: data.generatedAt, ...data.assessment, report: path.join(dir, 'index.html') }));
}
do {
  try { await collect(); }
  catch { console.error('health_report_collection_failed'); if (!process.argv.includes('--watch')) process.exitCode = 1; }
  if (!process.argv.includes('--watch')) break;
  await new Promise(resolve => setTimeout(resolve, 60000));
} while (true);
