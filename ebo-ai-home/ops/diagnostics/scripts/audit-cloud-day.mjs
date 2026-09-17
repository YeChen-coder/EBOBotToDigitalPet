import fs from 'node:fs';
import { readConfig } from '../src/common.mjs';
import { createAwsCli } from '../src/aws-cli.mjs';
import { safeCloudHealth } from '../src/aws-health.mjs';
import { classifyHealth } from '../src/probes.mjs';

// Explicit, read-only historical audit. The live reporter never runs this paid AWS scan.
const config = readConfig();
const host = JSON.parse(fs.readFileSync('local/aws-host.json', 'utf8').replace(/^\uFEFF/, ''));
const end = Date.now(), start = end - 86400000;
const report = { generatedAt: new Date(end).toISOString(), from: new Date(start).toISOString(), to: new Date(end).toISOString(), targets: [] };
fs.mkdirSync('local/health-report', { recursive: true });
for (const target of config.targets.filter(t => t.adapter === 'aws-ecs' && t.enabled !== false)) {
  const call = createAwsCli(host.connections[target.aws.connection], target);
  const identity = await call(['sts', 'get-caller-identity']);
  if (identity.Account !== target.aws.accountId || identity.Arn?.endsWith(':root')) throw new Error('identity_refused');
  const result = { target: target.id, containers: [] };
  for (const container of target.aws.containers.filter(c => c.probe !== 'container')) {
    let token, complete = false; const rows = new Map(); let invalid = 0;
    for (let page = 0; page < 150; page++) {
      const args = ['logs', 'filter-log-events', '--log-group-name', container.logGroup,
        '--log-stream-name-prefix', container.streamPrefix + '/',
        '--filter-pattern', '{ $.event = "health.snapshot" }', '--start-time', String(start), '--end-time', String(end), '--limit', '500', '--no-paginate'];
      if (token) args.push('--next-token', token);
      const data = await call(args);
      for (const e of data.events || []) {
        try {
          const r = JSON.parse(e.message);
          if (r.event !== 'health.snapshot' || r.schema_version !== 1 || r.service !== container.name) { invalid++; continue; }
          const health = safeCloudHealth(r.health, container.probe);
          const classified = container.probe === 'engine-health'
            ? { status: health.robot_count > 0 ? 'healthy' : 'fault', code: health.robot_count > 0 ? 'robot_connected' : 'engine_no_robot' }
            : classifyHealth(health, target, config);
          rows.set(e.eventId, { at: e.timestamp / 1000, taskId: e.logStreamName.split('/').at(-1), health, status: classified.status, code: classified.code });
        } catch { invalid++; }
      }
      if (!data.nextToken) { complete = true; break; }
      if (data.nextToken === token) break;
      token = data.nextToken;
    }
    const samples = [...rows.values()].sort((a, b) => a.at - b.at);
    const episodes = []; let open;
    let maxGapSeconds = samples.length ? Math.max(samples[0].at - start / 1000, end / 1000 - samples.at(-1).at) : 86400;
    const counters = {}; const previous = new Map();
    for (let n = 0; n < samples.length; n++) {
      const s = samples[n];
      if (n) maxGapSeconds = Math.max(maxGapSeconds, s.at - samples[n - 1].at);
      for (const key of ['media_recovery_attempts', 'unplanned_realtime_reconnects']) {
        const value = s.health[key], prior = previous.get(s.taskId)?.health[key];
        if (Number.isFinite(value) && Number.isFinite(prior) && value >= prior) counters[key] = (counters[key] || 0) + value - prior;
      }
      previous.set(s.taskId, s);
      if (s.status !== 'healthy') {
        if (!open || open.taskId !== s.taskId || open.code !== s.code) {
          open = { start: s.at, lastBadAt: s.at, taskId: s.taskId, code: s.code, status: s.status, samples: 0, recoveredAt: null }; episodes.push(open);
        }
        open.lastBadAt = s.at; open.samples++;
      } else if (open) { open.recoveredAt = s.at; open = null; }
    }
    fs.writeFileSync(`local/health-report/${target.id}-${container.name}-health.jsonl`, samples.map(s => JSON.stringify(s)).join('\n') + '\n');
    result.containers.push({ name: container.name, complete, invalid, count: samples.length,
      unhealthy: samples.filter(s => s.status === 'fault').length, suppressed: samples.filter(s => s.status === 'suppressed').length,
      firstAt: samples[0]?.at, lastAt: samples.at(-1)?.at, maxGapSeconds, taskIds: [...new Set(samples.map(s => s.taskId))], counters, episodes });
    console.log(JSON.stringify(result.containers.at(-1)));
  }
  report.targets.push(result);
}
fs.writeFileSync('local/health-report/cloud-day.json', JSON.stringify(report, null, 2));
console.log(`Historical audit: ${report.from} — ${report.to}`);
