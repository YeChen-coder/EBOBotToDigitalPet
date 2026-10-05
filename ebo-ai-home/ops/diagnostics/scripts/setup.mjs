import fs from 'node:fs';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repo = path.resolve(root, '../..');
process.chdir(root);
if (!fs.existsSync('.env')) {
  const content = fs.readFileSync('.env.example', 'utf8').replace(/^(BRIDGE_TOKEN|DIAGNOSTIC_TOKEN|WORKER_TOKEN|TRIAGE_WORKER_TOKEN)=$/gm, (_, k) => `${k}=${randomBytes(32).toString('hex')}`);
  fs.writeFileSync('.env', content, { mode: 0o600 });
}
// Backward-compatible upgrade: append missing variables, retaining existing API keys and choices.
let existing = fs.readFileSync('.env', 'utf8');
for (const line of fs.readFileSync('.env.example', 'utf8').split(/\r?\n/)) {
  const match = /^([A-Z_]+)=(.*)$/.exec(line);
  if (match && !new RegExp(`^${match[1]}=`, 'm').test(existing)) existing += `\n${match[1]}=${match[1].endsWith('_TOKEN') && match[1] === 'TRIAGE_WORKER_TOKEN' ? randomBytes(32).toString('hex') : match[2]}`;
}
fs.writeFileSync('.env', existing, { mode: 0o600 });
if (!fs.existsSync('config.local.json')) fs.copyFileSync('config.example.json', 'config.local.json');
fs.mkdirSync('local/source', { recursive: true });
// Explicit tracked-source allowlist: no .env, household data, recordings, HA configuration or .git.
const files = execFileSync('git', ['-c', `safe.directory=${repo.replaceAll('\\', '/')}`, '-C', repo, 'ls-files', '-z'], { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 }).split('\0');
const allowed = files.filter(f => /^(realtime-assistant\/|ha-enabot\/ebo\/)/.test(f) && /\.(py|sh|js|html)$/.test(f) && !/(^|\/)(tests?|private|vendor|node_modules)\//.test(f));
const staging = path.join(root, 'local/source');
// Refresh removes only obsolete files within this verified dedicated snapshot directory.
function prune(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isSymbolicLink()) throw new Error('Snapshot must not contain symlinks');
    if (entry.isDirectory()) prune(full);
    else if (!allowed.includes(path.relative(staging, full).replaceAll('\\', '/'))) fs.unlinkSync(full);
  }
}
prune(staging);
for (const relative of allowed) {
  const source = path.join(repo, relative); const target = path.join(staging, relative);
  if (!fs.realpathSync(source).startsWith(fs.realpathSync(repo) + path.sep)) throw new Error('Source escaped repository');
  fs.mkdirSync(path.dirname(target), { recursive: true }); fs.copyFileSync(source, target);
}
fs.writeFileSync(path.join(staging, 'snapshot.json'), JSON.stringify({ createdAt: new Date().toISOString(), commit: execFileSync('git', ['-c', `safe.directory=${repo.replaceAll('\\', '/')}`, '-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), files: allowed }, null, 2));
console.log(`Configuration ready; ${allowed.length} source files copied. Secrets were not printed. Observation-only mode is the initial default.`);
