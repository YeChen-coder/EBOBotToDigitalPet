import fs from 'node:fs';
import { readConfig } from '../src/common.mjs';
import { activeTargets } from '../src/environment.mjs';
import { AwsEcsAdapter } from '../src/aws-ecs.mjs';
import { createAwsCli } from '../src/aws-cli.mjs';

// One normal read-only round. No evidence expansion, actions, model calls or raw log output.
const config = readConfig();
const targets = activeTargets(config).filter(t => t.adapter === 'aws-ecs');
if (!targets.length) {
  console.log(JSON.stringify({ runtimeEnvironment: config.runtimeEnvironment, awsPolling: false, monthlyRounds: 0 }));
} else {
  const host = JSON.parse(fs.readFileSync(process.env.AWS_HOST_CONFIG_PATH || './local/aws-host.json', 'utf8').replace(/^\uFEFF/, ''));
  for (const target of targets) {
    const connection = { ...host.connections[target.aws.connection], allowRootReadOnce: false };
    const cli = createAwsCli(connection, target); const operations = {}; let responseBytes = 0;
    const call = async (args, options) => {
      const operation = args.slice(0, 2).join(' ');
      operations[operation] = (operations[operation] || 0) + 1;
      const result = await cli(args, options);
      responseBytes += Buffer.byteLength(JSON.stringify(result), 'utf8');
      return result;
    };
    const adapter = new AwsEcsAdapter(target, config, connection, { value: {}, save() {} }, call);
    const start = performance.now(); await adapter.refresh(true);
    const snapshot = adapter.snapshot();
    const monthlyRounds = 730 * 3600 / target.aws.pollSeconds;
    const payloadGiB = responseBytes * monthlyRounds / 1024 ** 3;
    console.log(JSON.stringify({ at: new Date().toISOString(), runtimeEnvironment: config.runtimeEnvironment,
      target: target.id, pollSeconds: target.aws.pollSeconds, logWindowSeconds: target.aws.logWindowSeconds,
      observation: snapshot.observation.code, error: snapshot.error || null, collectionErrors: snapshot.collectionErrors,
      operations, compactJsonResponseBytes: responseBytes, elapsedSeconds: +(performance.now() / 1000 - start / 1000).toFixed(2),
      monthlyHours: 730, monthlyRounds, projectedPayloadGiB: +payloadGiB.toFixed(3),
      projectedPayloadTransferUSDWithoutFreeTier: +(payloadGiB * 0.09).toFixed(3),
      caveat: 'Payload proxy, not metered transfer or an invoice; excludes protocol overhead, compression, fault evidence, other AWS traffic and AI usage. Assumed Canada internet egress rate USD 0.09/GB.' }, null, 2));
    if (snapshot.error || snapshot.collectionErrors?.length) process.exitCode = 1;
  }
}
