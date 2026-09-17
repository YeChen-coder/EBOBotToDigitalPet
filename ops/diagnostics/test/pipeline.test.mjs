import test from 'node:test';
import assert from 'node:assert/strict';
import { diagnose, pipelineConfig } from '../src/pipeline.mjs';
import { workerConfig } from '../src/worker-config.mjs';
import { Controller } from '../src/controller.mjs';
import { Jobs } from '../src/jobs.mjs';
const diagnosis = assessment => ({ assessment, summary: 'test', evidence: ['observed'], recommendations: ['check'] });
const request = { id: 'a', evidence: {}, timeoutSeconds: 300 };
const config = provider => pipelineConfig({ TRIAGE_PROVIDER: provider, TRIAGE_PROVIDER_URL: 'triage', ADVANCED_PROVIDER_URL: 'advanced' });
const signal = () => new AbortController().signal;
test('Codex stages have independent model, effort and deadline configuration', () => {
  assert.deepEqual(workerConfig({ CODEX_STAGE: 'triage' }), { stage: 'triage', model: 'gpt-5.6-luna', effort: 'low', maxSeconds: 90 });
  assert.equal(workerConfig({}).model, 'gpt-5.6-sol');
  assert.equal(workerConfig({ CODEX_MODEL: 'other-model', CODEX_REASONING_EFFORT: 'medium' }).model, 'other-model');
  assert.throws(() => workerConfig({ CODEX_REASONING_EFFORT: 'invalid' }));
  assert.throws(() => pipelineConfig({ TRIAGE_PROVIDER: 'typo' }));
});
test('Codex inconclusive triage passes evidence to advanced provider', async () => {
  const calls = [];
  const result = await diagnose(request, signal(), config('codex'), { remoteDiagnosis: async (r, s, p) => {
    calls.push({ r, p }); return { model: p.url, diagnosis: diagnosis(p.url === 'triage' ? 'inconclusive' : 'identified') };
  } });
  assert.equal(calls.length, 2); assert.equal(calls[0].r.id, 'a-triage'); assert.equal(calls[0].r.timeoutSeconds, 90);
  assert.equal(calls[1].r.evidence.triage.model, 'triage'); assert.equal(result.recoveryVerified, false);
});
test('identified first-line diagnosis avoids advanced cost without declaring recovery', async () => {
  let calls = 0;
  const result = await diagnose(request, signal(), config('codex'), { remoteDiagnosis: async () => { calls++; return { diagnosis: diagnosis('identified') }; } });
  assert.equal(calls, 1); assert.equal(result.advanced.reason, 'triage_identified'); assert.equal(result.recoveryVerified, false);
});
test('always escalation remains configurable', async () => {
  let calls = 0;
  await diagnose(request, signal(), { ...config('codex'), escalation: 'always' }, { remoteDiagnosis: async () => { calls++; return { diagnosis: diagnosis('identified') }; } });
  assert.equal(calls, 2);
});
test('original API adapter is still selectable and can complete first-line triage', async () => {
  let api = 0; let advanced = 0;
  await diagnose(request, signal(), config('api'), { apiTriage: async () => { api++; return diagnosis('identified'); }, remoteDiagnosis: async () => advanced++ });
  assert.equal(api, 1); assert.equal(advanced, 0);
});
test('missing API, disabled triage and provider failure escalate', async () => {
  for (const provider of ['api', 'disabled', 'codex']) {
    let advanced = 0;
    const r = await diagnose(request, signal(), config(provider), { apiTriage: async () => ({ skipped: true }),
      remoteDiagnosis: async (r, s, p) => { if (p.url === 'triage') throw new Error('failure'); advanced++; return { diagnosis: diagnosis('identified') }; } });
    assert.equal(advanced, 1); assert.equal(r.recoveryVerified, false);
  }
});
test('cancellation cannot launch advanced after first line returns', async () => {
  const controller = new AbortController(); let calls = 0;
  await assert.rejects(diagnose(request, controller.signal, config('codex'), { remoteDiagnosis: async () => {
    calls++; controller.abort(); return { diagnosis: diagnosis('inconclusive') };
  } })); assert.equal(calls, 1);
});
test('switching to observation-only cancels active work and preserves recovery budget', async () => {
  let cancelled = 0;
  const store = { value: { incident: { id: 'a', phase: 'diagnosing', jobSubmitted: true, observations: [] }, recoveries: [{ target: 'x', at: 1 }] }, save() {} };
  const c = new Controller(store, { observationOnly: true, targets: [], repeatWindowSeconds: 1000 }, { cancel: async () => cancelled++ });
  await c.tick({ status: 'fault', target: 'x', code: 'failed' }, 50);
  assert.equal(cancelled, 1); assert.equal(store.value.incident.jobSubmitted, false); assert.equal(store.value.recoveries.length, 1);
});
test('report index is bounded and omits evidence and credentials', async () => {
  const jobs = new Jobs({ value: { jobs: { a: { id: 'a', status: 'completed', createdAt: 1, request: { evidence: 'private' }, result: { summary: 'private' } } } }, save() {} }, async () => {});
  assert.deepEqual(await jobs.route('GET', '/jobs'), { jobs: [{ id: 'a', status: 'completed', createdAt: 1, endedAt: undefined }] });
});
