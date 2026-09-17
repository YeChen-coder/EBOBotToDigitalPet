import test from 'node:test';
import assert from 'node:assert/strict';
import { assessHealth, incidentRows, renderReport } from '../src/health-report.mjs';
import { Controller } from '../src/controller.mjs';

function good() {
  return { generatedAt: new Date(1000000).toISOString(), state: { runtimeEnvironment: 'aws', lastTick: 1000, lastSample: { status: 'healthy', evidence: { samples: [] } } },
    watcher: { ok: true, mode: 'active' }, bridge: { ok: true, runtimeEnvironment: 'aws' },
    containers: ['watcher','diagnostic-service','codex-triage','codex-worker'].map(service => ({ service, status: 'running', health: 'healthy' })),
    providers: Object.fromEntries(['diagnostic-service','codex-triage','codex-worker'].map(n => [n, { health: { ok: true, credentialConfigured: true }, jobs: [] }])) };
}
test('stale Watcher cannot give a green business or agent status', () => {
  assert.equal(assessHealth(good(), 1001).agent, 'healthy');
  assert.equal(assessHealth(good(), 1200).business, 'unknown');
  assert.equal(assessHealth(good(), 1200).agent, 'attention');
});
test('missing worker credentials and stuck jobs are not healthy', () => {
  const data = good(); data.providers['codex-triage'].health.credentialConfigured = false;
  data.providers['codex-worker'].jobs.push({ id: 'stuck', status: 'running', createdAt: 100, timeoutSeconds: 300 });
  const h = assessHealth(data, 1001);
  assert.equal(h.issues.length, 2);
});
test('failed real diagnostics are shown even when worker processes are healthy', () => {
  const data=good(); data.providers['codex-worker'].jobs.push({id:'real',createdAt:900,status:'failed',error:'execution_failed'});
  assert.equal(assessHealth(data,1001).agent,'attention');
  assert.ok(assessHealth(data,1001).issues.some(x=>x.includes('实际诊断失败')));
});
test('stale cloud cache is unknown even if saved sample says healthy', () => {
  const data = good(); data.state.lastSample.evidence.samples.push({ target: 'cloud-ebo', evidence: { cloud: { observedAt: 700 } } });
  assert.equal(assessHealth(data, 1001).business, 'unknown');
});
test('closed incident retains original cause, task and action without raw observations', () => {
  const c = new Controller({}, {}, {});
  const i = { id: 'incident-1', target: 'cloud-ebo', code: 'aws_video_stalled', startedAt: 10, phase: 'recovering',
    action: { status: 'issued' }, observations: [{ evidence: { cloud: { tasks: [{ taskArn: 'arn:aws:task/id-1' }] } } }] };
  const record = c.closeRecord(i, 20, 'recovered_after_action');
  const rows = incidentRows({ scopes: { 'cloud-ebo': { closed: [record] } } }, {});
  assert.equal(rows[i.id].code, i.code); assert.deepEqual(rows[i.id].taskIds, ['id-1']);
  assert.equal(rows[i.id].tier, '固定规则恢复'); assert.equal(rows[i.id].observations, undefined);
});
test('older incidents remain unknown and retain observed detail on later closure', () => {
  const observed = { id: 'i', code: 'aws_snapshot_stale', phase: 'monitoring_failed', startedAt: 10 };
  const archive = incidentRows({ scopes: { cloud: { incident: observed } } }, {});
  const rows = incidentRows({ scopes: { cloud: { closed: [{ id: 'i', outcome: 'recovered', endedAt: 20 }] } } }, {}, archive);
  assert.equal(rows.i.code, 'aws_snapshot_stale'); assert.equal(rows.i.phase, 'closed');
  const old = incidentRows({ scopes: { cloud: { closed: [{ id: 'old', outcome: 'recovered' }] } } }, {});
  assert.equal(old.old.code, '历史未保留故障原因');
});
test('reports escape model text and include stale-output detection', () => {
  const data = good(); data.assessment = assessHealth(data, 1001); data.incidents = {};
  data.providers['codex-worker'].jobs.push({ id: 'smoke-x', result: { diagnosis: { summary: '<script>attack()</script>' } } });
  const html = renderReport(data);
  assert.ok(html.includes('&lt;script&gt;attack()&lt;/script&gt;'));
  assert.ok(html.includes('报告已过期')); assert.ok(html.includes('安装测试'));
});
test('full report renders English for the dashboard while retaining Chinese support', () => {
  const data=good();data.assessment=assessHealth(data,1001);data.incidents={};
  const english=renderReport(data,'en'),chinese=renderReport(data,'zh');
  assert.match(english,/<html lang="en">/);assert.ok(english.includes('Diagnostic Agent evidence'));assert.ok(english.includes('Current components'));
  assert.match(chinese,/<html lang="zh-CN">/);assert.ok(chinese.includes('Diagnostic Agent 详细证据'));
});
