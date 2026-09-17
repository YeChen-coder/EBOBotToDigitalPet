import { validId, now, failure } from './common.mjs';

export class Jobs {
  constructor(store, run, { maxSeconds = 600, maxQueued = 8 } = {}) {
    this.store = store; this.run = run; this.maxSeconds = maxSeconds; this.maxQueued = maxQueued;
    this.active = null;
    // An interrupted paid run is not retried implicitly; preserve the evidence and fail visibly.
    for (const job of Object.values(store.value.jobs)) {
      if (job.status === 'running') Object.assign(job, { status: 'failed', error: 'worker_restarted', endedAt: now() });
    }
    store.save();
    queueMicrotask(() => this.pump());
  }
  async route(method, url, body) {
    if (method === 'GET' && url === '/jobs') return { jobs: Object.values(this.store.value.jobs)
      .sort((a, b) => b.createdAt - a.createdAt).slice(0, 30).map(j => ({ id: j.id, status: j.status, createdAt: j.createdAt, endedAt: j.endedAt })) };
    if (method === 'POST' && url === '/jobs') {
      if (!validId(body.id) || body.schemaVersion !== 1 || typeof body.evidence !== 'object' || !Number.isFinite(body.timeoutSeconds) || body.timeoutSeconds < 1) return { code: 400, body: { error: 'invalid_job' } };
      const prior = this.store.value.jobs[body.id];
      if (prior) return this.public(prior);
      if (Object.values(this.store.value.jobs).filter(j => ['queued', 'running'].includes(j.status)).length >= this.maxQueued) return { code: 429, body: { error: 'queue_full' } };
      const job = this.store.value.jobs[body.id] = { id: body.id, status: 'queued', createdAt: now(), request: body };
      this.store.save(); queueMicrotask(() => this.pump());
      return { code: 202, body: this.public(job) };
    }
    const match = /^\/jobs\/([a-zA-Z0-9_-]{1,100})(\/cancel)?$/.exec(url);
    if (!match || !this.store.value.jobs[match[1]]) return { code: 404, body: { error: 'not_found' } };
    const job = this.store.value.jobs[match[1]];
    if (method === 'POST' && match[2]) {
      if (['queued', 'running'].includes(job.status)) {
        job.status = 'cancelled'; job.endedAt = now();
        if (this.active?.id === job.id) this.active.controller.abort();
        this.store.save();
      }
      return this.public(job);
    }
    if (method === 'GET' && !match[2]) return this.public(job);
    return { code: 405, body: { error: 'method_not_allowed' } };
  }
  public(job) {
    const { request, ...result } = job;
    return result;
  }
  async pump() {
    if (this.active) return;
    const job = Object.values(this.store.value.jobs).find(j => j.status === 'queued');
    if (!job) return;
    const controller = new AbortController();
    this.active = { id: job.id, controller };
    job.status = 'running'; job.startedAt = now(); this.store.save();
    const timer = setTimeout(() => controller.abort(new DOMException('deadline', 'TimeoutError')), Math.min(job.request.timeoutSeconds, this.maxSeconds) * 1000);
    try {
      const result = await this.run(job.request, controller.signal);
      controller.signal.throwIfAborted();
      if (job.status !== 'cancelled') Object.assign(job, { status: 'completed', result });
    } catch (error) {
      if (job.status !== 'cancelled') Object.assign(job, controller.signal.aborted ? { status: 'failed', error: 'timeout' } : failure(error));
    } finally {
      clearTimeout(timer); job.endedAt = now(); this.active = null;
      // Retain bounded report history. UUIDs aren't reused by Watcher after closure.
      const done = Object.values(this.store.value.jobs).filter(j => !['queued', 'running'].includes(j.status)).sort((a, b) => a.createdAt - b.createdAt);
      for (const old of done.slice(0, -100)) delete this.store.value.jobs[old.id];
      this.store.save(); queueMicrotask(() => this.pump());
    }
  }
}
