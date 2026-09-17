import fs from 'node:fs';
import { readConfig } from '../src/common.mjs';

const config = readConfig();
const [operation, value] = process.argv.slice(2);
if (operation === 'environment') {
  if (!['local', 'aws'].includes(value)) throw new Error('Choose local or aws');
  config.runtimeEnvironment = value;
} else if (operation === 'sampling') {
  const seconds = Number(value);
  if (!Number.isInteger(seconds) || seconds < 30 || seconds > 3600) throw new Error('AWS interval must be 30..3600 seconds');
  const targets = config.targets.filter(t => t.adapter === 'aws-ecs' && t.enabled !== false);
  if (!targets.length) throw new Error('No enabled AWS targets configured');
  for (const t of targets) {
    t.aws.pollSeconds = seconds;
    t.aws.snapshotMaxAgeSeconds = Math.max(t.aws.snapshotMaxAgeSeconds, seconds * 2);
  }
} else throw new Error('Use environment local|aws or sampling SECONDS');
// Validate before replacing the real configuration, including selected-target existence.
const file = process.env.CONFIG_PATH || './config.local.json';
const staged = file + '.staged'; const previousPath = process.env.CONFIG_PATH;
try {
  fs.writeFileSync(staged, JSON.stringify(config, null, 2) + '\n', { mode: 0o600 });
  process.env.CONFIG_PATH = staged; readConfig();
  fs.renameSync(staged, file);
} finally {
  if (previousPath === undefined) delete process.env.CONFIG_PATH; else process.env.CONFIG_PATH = previousPath;
  if (fs.existsSync(staged)) fs.unlinkSync(staged);
}
console.log(`${operation}: ${value}. Reload the host bridge and Watcher to apply. Business deployments are not started or stopped.`);
