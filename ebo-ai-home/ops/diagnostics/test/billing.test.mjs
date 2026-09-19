import test from 'node:test';
import assert from 'node:assert/strict';
import { BillingMonitor, parseAwsCosts, parseOpenAICosts } from '../src/billing.mjs';

const memory = value => ({ value, saves: 0, save() { this.saves++; } });

test('OpenAI daily costs are summed into month-to-date and latest-day values', () => {
  const costs = parseOpenAICosts({ data: [
    { start_time: 1788220800, results: [{ amount: { value: 1.25, currency: 'usd' } }] },
    { start_time: 1788307200, results: [{ amount: { value: 0.5, currency: 'usd' } }, { amount: { value: 0.2, currency: 'usd' } }] },
  ], has_more: false });
  assert.deepEqual(costs.monthToDate, { amount: 1.95, currency: 'USD' });
  assert.deepEqual(costs.latestDay, { amount: 0.7, currency: 'USD', date: '2026-09-02' });
});

test('AWS daily unblended cost is parsed without treating missing days as an error', () => {
  const costs = parseAwsCosts({ ResultsByTime: [
    { TimePeriod: { Start: '2026-09-01' }, Total: { UnblendedCost: { Amount: '2.10', Unit: 'USD' } }, Estimated: false },
    { TimePeriod: { Start: '2026-09-02' }, Total: { UnblendedCost: { Amount: '0.40', Unit: 'USD' } }, Estimated: true },
  ] });
  assert.deepEqual(costs.monthToDate, { amount: 2.5, currency: 'USD' });
  assert.deepEqual(costs.latestDay, { amount: 0.4, currency: 'USD', date: '2026-09-02' });
  assert.equal(costs.estimated, true);
});

test('billing monitor caches both providers and does not query again before their intervals', async () => {
  let at = Date.UTC(2026, 8, 18, 12) / 1000; let openAICalls = 0; let awsCalls = 0;
  const store = memory({});
  const response = { ok: true, headers: new Headers(), text: async () => JSON.stringify({ data: [
    { start_time: Date.UTC(2026, 8, 18) / 1000, results: [{ amount: { value: 0.75, currency: 'usd' } }] },
  ], has_more: false }) };
  const monitor = new BillingMonitor({ store, openAIKey: 'sk-admin-test', clock: () => at,
    fetchImpl: async () => { openAICalls++; return response; },
    awsCall: async args => { awsCalls++; assert.deepEqual(args.slice(0, 2), ['ce', 'get-cost-and-usage']); return { ResultsByTime: [
      { TimePeriod: { Start: '2026-09-17' }, Total: { UnblendedCost: { Amount: '1.50', Unit: 'USD' } }, Estimated: true },
    ] }; }, openAIPollSeconds: 900, awsPollSeconds: 21600 });
  await monitor.poll();
  assert.equal(monitor.view().openai.status, 'ok'); assert.equal(monitor.view().aws.status, 'ok');
  assert.equal(openAICalls, 1); assert.equal(awsCalls, 1);
  at += 899; await monitor.poll(); assert.equal(openAICalls, 1); assert.equal(awsCalls, 1);
  at += 1; await monitor.poll(); assert.equal(openAICalls, 2); assert.equal(awsCalls, 1);
  assert.ok(store.saves >= 5);
});

test('billing monitor exposes configuration failures without leaking credentials', () => {
  const monitor = new BillingMonitor({ store: memory({}), openAIKey: '', awsCall: null });
  const view = monitor.view();
  assert.equal(view.openai.status, 'unconfigured'); assert.equal(view.aws.status, 'unconfigured');
  assert.equal(JSON.stringify(view).includes('Bearer'), false);
});

test('a restarted monitor immediately validates OpenAI credentials without bypassing the AWS interval', async () => {
  const at = Date.UTC(2026, 8, 18, 12) / 1000; let openAICalls = 0; let awsCalls = 0;
  const store = memory({
    openai: { status: 'ok', error: null, observedAt: at - 60, nextPollAt: at + 840,
      monthToDate: { amount: 0, currency: 'USD' }, latestDay: null, estimated: true },
    aws: { status: 'ok', error: null, observedAt: at - 60, nextPollAt: at + 20000,
      monthToDate: { amount: 1, currency: 'USD' }, latestDay: null, estimated: true },
  });
  const monitor = new BillingMonitor({ store, openAIKey: 'sk-admin-rotated', clock: () => at,
    fetchImpl: async () => { openAICalls++; return { ok: true, headers: new Headers(), text: async () => JSON.stringify({ data: [], has_more: false }) }; },
    awsCall: async () => { awsCalls++; return { ResultsByTime: [] }; } });
  await monitor.poll();
  assert.equal(openAICalls, 1);
  assert.equal(awsCalls, 0);
});
