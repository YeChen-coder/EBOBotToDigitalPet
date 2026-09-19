const OPENAI_POLL_SECONDS = 15 * 60;
const AWS_POLL_SECONDS = 6 * 60 * 60;

const initialProvider = configured => ({
  status: configured ? 'pending' : 'unconfigured',
  error: configured ? null : 'credentials_not_configured',
  checkedAt: null,
  observedAt: null,
  nextPollAt: configured ? 0 : null,
  monthToDate: null,
  latestDay: null,
  estimated: true,
});

function utcDate(epochSeconds) {
  return new Date(epochSeconds * 1000).toISOString().slice(0, 10);
}

function monthStart(epochSeconds) {
  const date = new Date(epochSeconds * 1000);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1) / 1000;
}

function nextUtcDate(epochSeconds) {
  const date = new Date(epochSeconds * 1000);
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + 1)).toISOString().slice(0, 10);
}

function money(value, currency) {
  const amount = Number(value);
  if (!Number.isFinite(amount) || typeof currency !== 'string' || !currency) throw new Error('billing_response_invalid');
  return { amount, currency: currency.toUpperCase() };
}

function addMoney(total, item) {
  if (!total) return { ...item };
  if (total.currency !== item.currency) throw new Error('billing_currency_mismatch');
  total.amount += item.amount;
  return total;
}

function normalizeError(provider, error) {
  const message = String(error?.message || '');
  if (provider === 'openai') {
    if (message === 'http_401' || message === 'http_403') return 'openai_billing_access_denied';
    if (message === 'http_429') return 'openai_rate_limited';
    return ['billing_response_invalid', 'billing_currency_mismatch'].includes(message) ? message : 'openai_billing_unavailable';
  }
  return ['aws_access_denied', 'aws_credentials_unavailable', 'aws_throttled'].includes(message) ? message : 'aws_billing_unavailable';
}

async function boundedJson(response) {
  if (!response.ok) throw new Error(`http_${response.status}`);
  const length = Number(response.headers?.get?.('content-length') || 0);
  if (length > 512 * 1024) throw new Error('billing_response_invalid');
  const text = await response.text();
  if (text.length > 512 * 1024) throw new Error('billing_response_invalid');
  try { return JSON.parse(text); } catch { throw new Error('billing_response_invalid'); }
}

export function parseOpenAICosts(payload) {
  if (!Array.isArray(payload?.data) || payload.has_more) throw new Error('billing_response_invalid');
  let monthToDate = null; let latestDay = null;
  for (const bucket of payload.data) {
    if (!Number.isFinite(bucket?.start_time) || !Array.isArray(bucket.results)) throw new Error('billing_response_invalid');
    let daily = null;
    for (const result of bucket.results) daily = addMoney(daily, money(result?.amount?.value, result?.amount?.currency));
    if (!daily) continue;
    monthToDate = addMoney(monthToDate, daily);
    if (!latestDay || bucket.start_time > latestDay.startTime) latestDay = { ...daily, date: utcDate(bucket.start_time), startTime: bucket.start_time };
  }
  if (!monthToDate) monthToDate = { amount: 0, currency: 'USD' };
  if (latestDay) delete latestDay.startTime;
  return { monthToDate, latestDay };
}

export function parseAwsCosts(payload) {
  if (!Array.isArray(payload?.ResultsByTime) || payload.NextPageToken) throw new Error('billing_response_invalid');
  let monthToDate = null; let latestDay = null; let estimated = false;
  for (const result of payload.ResultsByTime) {
    const metric = result?.Total?.UnblendedCost;
    if (!metric) continue;
    const daily = money(metric.Amount, metric.Unit);
    monthToDate = addMoney(monthToDate, daily);
    const date = result?.TimePeriod?.Start;
    if (typeof date !== 'string') throw new Error('billing_response_invalid');
    if (!latestDay || date > latestDay.date) latestDay = { ...daily, date };
    estimated ||= result.Estimated === true;
  }
  if (!monthToDate) monthToDate = { amount: 0, currency: 'USD' };
  return { monthToDate, latestDay, estimated };
}

export class BillingMonitor {
  constructor({ store, awsCall, openAIKey = '', fetchImpl = fetch, clock = () => Date.now() / 1000,
    openAIPollSeconds = OPENAI_POLL_SECONDS, awsPollSeconds = AWS_POLL_SECONDS }) {
    this.store = store;
    this.awsCall = awsCall;
    this.openAIKey = openAIKey;
    this.fetch = fetchImpl;
    this.clock = clock;
    this.intervals = { openai: openAIPollSeconds, aws: awsPollSeconds };
    this.configured = { openai: !!openAIKey, aws: typeof awsCall === 'function' };
    this.inFlight = new Set();
    this.store.value ||= {};
    for (const provider of ['openai', 'aws']) {
      if (!this.store.value[provider]) this.store.value[provider] = initialProvider(this.configured[provider]);
      if (!this.configured[provider]) this.store.value[provider] = initialProvider(false);
      else if (this.store.value[provider].status === 'unconfigured') this.store.value[provider] = initialProvider(true);
      else if (this.store.value[provider].status === 'error') this.store.value[provider].nextPollAt = 0;
      // The Admin Key is deliberately never persisted, so a restarted process cannot
      // compare it with the previous credential. Refresh OpenAI once at startup to
      // validate key rotations immediately; keep the paid AWS Cost Explorer cadence.
      else if (provider === 'openai') this.store.value[provider].nextPollAt = 0;
    }
    this.store.save();
  }

  view() {
    return structuredClone(this.store.value);
  }

  async poll() {
    const now = this.clock();
    const pending = [];
    for (const provider of ['openai', 'aws']) {
      const state = this.store.value[provider];
      if (this.configured[provider] && !this.inFlight.has(provider) && now >= (state.nextPollAt || 0)) pending.push(this.#refresh(provider, now));
    }
    await Promise.allSettled(pending);
  }

  async #refresh(provider, startedAt) {
    this.inFlight.add(provider);
    const previous = this.store.value[provider];
    this.store.value[provider] = { ...previous, status: previous.observedAt ? 'refreshing' : 'pending', checkedAt: startedAt };
    this.store.save();
    try {
      const costs = provider === 'openai' ? await this.#openAI(startedAt) : await this.#aws(startedAt);
      const observedAt = this.clock();
      this.store.value[provider] = { status: 'ok', error: null, checkedAt: observedAt, observedAt,
        nextPollAt: observedAt + this.intervals[provider], estimated: costs.estimated ?? true,
        monthToDate: costs.monthToDate, latestDay: costs.latestDay };
    } catch (error) {
      const checkedAt = this.clock();
      this.store.value[provider] = { ...previous, status: previous.observedAt ? 'stale' : 'error',
        error: normalizeError(provider, error), checkedAt, nextPollAt: checkedAt + this.intervals[provider] };
    } finally {
      this.store.save();
      this.inFlight.delete(provider);
    }
  }

  async #openAI(at) {
    const params = new URLSearchParams({ start_time: String(monthStart(at)), end_time: String(Math.floor(at)), bucket_width: '1d', limit: '31' });
    const response = await this.fetch(`https://api.openai.com/v1/organization/costs?${params}`, {
      headers: { authorization: `Bearer ${this.openAIKey}`, 'content-type': 'application/json' },
      redirect: 'error', signal: AbortSignal.timeout(15000),
    });
    return parseOpenAICosts(await boundedJson(response));
  }

  async #aws(at) {
    const start = utcDate(monthStart(at)); const end = nextUtcDate(at);
    const payload = await this.awsCall(['ce', 'get-cost-and-usage', '--time-period', `Start=${start},End=${end}`,
      '--granularity', 'DAILY', '--metrics', 'UnblendedCost']);
    return parseAwsCosts(payload);
  }
}
