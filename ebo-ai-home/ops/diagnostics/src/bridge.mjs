import { validId, now } from './common.mjs';
import { activeTargets } from './environment.mjs';

export class ActionBridge {
  constructor(store, config, io) { this.store = store; this.c = config; this.io = io; }
  async route(method, url, body) {
    if (method === 'GET' && url === '/snapshot') return this.io.snapshot();
    if (method === 'POST' && url === '/evidence') {
      const t = activeTargets(this.c).find(t => t.id === body.target);
      if (!t) return { code: 403, body: { error: 'target_not_allowed' } };
      return this.io.evidence(t.container, t);
    }
    if (method === 'POST' && url === '/notify') {
      if (!validId(body.id) || typeof body.message !== 'string' || body.message.length > 1200) return { code: 400, body: { error: 'invalid_notification' } };
      if (this.store.value.notifications[body.id]) return { delivered: true };
      await this.io.notify(body.message);
      this.store.value.notifications[body.id] = now(); this.store.save();
      return { delivered: true };
    }
    if (method !== 'POST' || url !== '/restart') return { code: 404, body: { error: 'not_found' } };
    const t = activeTargets(this.c).find(t => t.id === body.target);
    if (!validId(body.id) || !t || !t.restartOnStall || t.maintenance || this.c.maintenance || !this.c.autoRecovery || this.c.observationOnly) return { code: 403, body: { error: 'action_not_allowed' } };
    const prior = this.store.value.actions[body.id];
    if (prior) return prior;
    if (Object.values(this.store.value.actions).some(a => a.target === t.id && now() - a.at < this.c.repeatWindowSeconds)) return { code: 409, body: { error: 'target_cooldown' } };
    let context;
    if (t.adapter === 'aws-ecs') {
      try { context = await this.io.prepareRestart(t); }
      catch { return { code: 409, body: { error: 'aws_recovery_not_applicable' } }; }
    } else {
      const snap = await this.io.snapshot();
      if (!snap.dockerOk || snap.targets[t.id]?.status !== 'running') return { code: 409, body: { error: 'target_not_running' } };
    }
    // Recheck after await: another concurrent request might have reserved this target.
    if (!activeTargets(this.c).some(x => x.id === t.id) || this.io.actionsBlocked?.()) return { code: 409, body: { error: 'runtime_changed' } };
    if (Object.values(this.store.value.actions).some(a => a.target === t.id && now() - a.at < this.c.repeatWindowSeconds)) return { code: 409, body: { error: 'target_cooldown' } };
    const action = this.store.value.actions[body.id] = { id: body.id, target: t.id, at: now(), status: 'reserved', context };
    this.store.save();
    // The caller gets an acknowledgement before docker restart's stop timeout.
    Promise.resolve().then(() => this.io.restart(t.container, t, context)).then(() => { action.status = 'completed'; }, () => { action.status = 'failed_or_uncertain'; }).finally(() => this.store.save());
    return { code: 202, body: action };
  }
}

export class Guardian {
  constructor(store, config, io) { this.store = store; this.c = config; this.io = io; }
  async tick(healthy, at) {
    const s = this.store.value;
    if (healthy) {
      if (s.outage) {
        s.goodSince ??= at;
        if (at - s.goodSince < this.c.healthySeconds) { this.store.save(); return; }
      }
      s.outage = null; s.goodSince = null; this.store.save(); return;
    }
    s.goodSince = null;
    s.outage ??= { startedAt: at };
    const o = s.outage;
    if (at - o.startedAt < this.c.confirmSeconds) { this.store.save(); return; }
    if (this.c.guardianAutoRestart && !this.c.maintenance && !this.c.observationOnly && !o.attempted && (!s.lastRestart || at - s.lastRestart > this.c.repeatWindowSeconds)) {
      o.attempted = true; o.actionAt = at; s.lastRestart = at; this.store.save();
      try { await this.io.restartDocker(); } catch { o.restartFailed = true; }
    }
    if (!o.notified && at - o.startedAt >= this.c.notifySeconds) {
      try { await this.io.notify('EBO: Docker 引擎持续不可用，容器内诊断暂时不能运行，请检查 Docker Desktop。'); o.notified = true; }
      catch { o.notificationFailed = true; }
    }
    this.store.save();
  }
}
