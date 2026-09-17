import fs from 'node:fs';
import path from 'node:path';
import { readConfig, Store } from '../src/common.mjs';
import { AwsEcsAdapter } from '../src/aws-ecs.mjs';
import { createAwsCli } from '../src/aws-cli.mjs';
import { activeTargets } from '../src/environment.mjs';

const config = readConfig();
const host = JSON.parse(fs.readFileSync(process.env.AWS_HOST_CONFIG_PATH || './local/aws-host.json', 'utf8').replace(/^\uFEFF/, ''));
const output = [];
for (const target of activeTargets(config).filter(t => t.adapter === 'aws-ecs')) {
  const connection = { ...host.connections[target.aws.connection], allowRootReadOnce: process.argv.includes('--one-time-root-read') };
  // Test state is independent of the running bridge's persistent action/recovery state.
  const adapter = new AwsEcsAdapter(target, config, connection, new Store(path.join('local/aws-check', `${target.id}.json`), {}), createAwsCli(connection, target));
  await adapter.refresh(true);
  const state = process.argv.includes('--evidence') ? await adapter.evidence() : adapter.snapshot();
  output.push({ target: target.id, ...state });
}
console.log(JSON.stringify(output, null, 2));
if (!output.length || output.some(x => x.error)) process.exitCode = 1;
