import { randomUUID } from 'node:crypto';

// Dependencies are injected so fault timelines can be tested without Docker or a model.
export class Controller {
  constructor(store, config, io) { this.store = store; this.c = config; this.io = io; }
  closeRecord(i, at, outcome) {
    return { id: i.id, target: i.target, code: i.code, startedAt: i.startedAt, endedAt: at, outcome,
      lastPhase: i.phase, notified: i.notified, jobSubmitted: i.jobSubmitted === true,
      jobStatus: i.job?.status || null, action: i.action || null,
      taskIds: [...new Set((i.observations || []).flatMap(o => o.evidence?.cloud?.tasks?.map(t => t.taskArn?.split('/').at(-1)).filter(Boolean) || []))] };
  }
  async tick(sample, at) {
    const s = this.store.value;
    const counts = Object.fromEntries((sample.evidence?.samples || [sample]).filter(x => Number.isFinite(x.evidence?.container?.restartCount)).map(x => [x.target, x.evidence.container.restartCount]));
    s.restartSamples = (s.restartSamples || []).filter(x => at - x.at < this.c.repeatWindowSeconds);
    for (const [target, count] of Object.entries(counts)) {
      if (this.c.targets.find(t => t.id === target)?.maintenance) continue;
      if (!this.c.maintenance && s.restartSamples.some(x => Number.isFinite(x.counts[target]) && count - x.counts[target] >= 3)) {
        sample = { ...sample, status: 'fault', code: 'container_restart_storm', target, recoverable: false }; break;
      }
    }
    s.restartSamples.push({ at, counts });
    s.lastTick = at; s.lastSample = sample;
    s.recoveries = (s.recoveries || []).filter(x => at - x.at < this.c.repeatWindowSeconds);
    s.history = [...(s.history || []), { at, ...sample }].slice(-20);
    let i = s.incident;
    if (this.c.observationOnly && i?.jobSubmitted) {
      await this.io.cancel(i.id);
      i.jobSubmitted = false; i.phase = 'pending'; i.id = randomUUID(); i.badSince = at;
    }
    if (sample.status === 'healthy') {
      s.previousStatus = 'healthy';
      if (!i) { this.store.save(); return; }
      i.healthySince ??= at;
      const observedAt = sample.evidence?.cloud?.observedAt;
      if (at - i.healthySince >= this.c.healthySeconds && (observedAt === undefined || observedAt >= i.healthySince + this.c.healthySeconds)) {
        if (i.jobSubmitted) await this.io.cancel(i.id).catch(() => {});
        if (i.notified && !this.c.observationOnly) {
          try { await this.io.notify(i, 'recovered'); } catch { this.store.save(); return; }
        }
        s.closed = [...(s.closed || []), this.closeRecord(i, at, i.action ? 'recovered_after_action' : 'recovered')].slice(-100);
        s.incident = null;
      }
      this.store.save(); return;
    }
    if (sample.status === 'suppressed') {
      s.previousStatus = 'suppressed';
      if (i?.jobSubmitted) await this.io.cancel(i.id).catch(() => {});
      if (i) s.closed = [...(s.closed || []), this.closeRecord(i, at, 'suppressed_not_verified')].slice(-100);
      s.incident = null; this.store.save(); return;
    }
    if (sample.status === 'grace') {
      s.previousStatus = 'grace';
      if (i) { i.healthySince = null; await this.maybeNotify(i, at); }
      this.store.save(); return;
    }
    if (!i) {
      i = s.incident = { id: randomUUID(), startedAt: at, phase: 'pending', target: sample.target, code: sample.code, observations: [], notified: false };
    }
    i.healthySince = null;
    i.observations = [...i.observations, { at, ...sample }].slice(-20);
    // Reset pending confirmation after intermittent health, and never interpret model text as recovery.
    i.badSince ??= at;
    i.badEvidenceAt ??= sample.evidence?.cloud?.observedAt;
    if (s.previousStatus && s.previousStatus !== 'fault' && i.phase === 'pending') { i.badSince = at; i.badEvidenceAt = sample.evidence?.cloud?.observedAt; }
    s.previousStatus = 'fault';
    if (sample.diagnosticEligible === false) {
      // Missing observation credentials/connectivity requires operator action, not a paid diagnosis.
      if (i.jobSubmitted) await this.io.cancel(i.id).catch(() => {});
      i.phase = 'monitoring_failed'; i.target = sample.target; i.code = sample.code;
      await this.maybeNotify(i, at); this.store.save(); return;
    }
    if (i.phase === 'monitoring_failed') {
      i.phase = 'pending'; i.badSince = at; i.jobSubmitted = false;
      // Use a fresh job ID after cancelling an earlier incident's work.
      i.id = randomUUID(); i.notified = false;
    }
    if (i.phase === 'pending' && at - i.badSince >= this.c.confirmSeconds &&
        (i.badEvidenceAt === undefined || sample.evidence?.cloud?.observedAt > i.badEvidenceAt)) {
      i.target = sample.target; i.code = sample.code;
      if (this.io.evidence && !this.c.observationOnly) {
        try { i.initialEvidence = await this.io.evidence(sample.target); } catch { i.initialEvidence = { unavailable: true }; }
      }
      const repeated = s.recoveries.some(x => x.target === sample.target);
      if (sample.recoverable && !repeated && this.c.autoRecovery && !this.c.observationOnly) {
        i.target = sample.target; i.code = sample.code;
        i.phase = 'recovering'; i.action = { id: `${i.id}-restart`, at, status: 'reserved', waitSeconds: sample.recoverySeconds || this.c.recoverySeconds };
        s.recoveries.push({ at, target: sample.target });
        this.store.save(); // Reserve before the network request. Never repeat an uncertain write.
        try { i.action.result = await this.io.restart(sample.target, i.action.id); i.action.status = 'issued'; }
        catch { i.action.status = 'uncertain'; }
      } else i.phase = 'diagnosis_pending';
    }
    if (i.phase === 'recovering' && at - i.action.at >= (i.action.waitSeconds || this.c.recoverySeconds)) i.phase = 'diagnosis_pending';
    this.store.save();
    if (i.phase === 'diagnosis_pending' && !this.c.observationOnly) {
      try {
        if (this.io.evidence && !i.finalEvidence) i.finalEvidence = await this.io.evidence(sample.target).catch(() => ({ unavailable: true }));
        const job = await this.io.submit({ id: i.id, schemaVersion: 1, target: i.target, symptom: i.code,
          evidence: { observations: i.observations, history: s.history, initial: i.initialEvidence, afterRecovery: i.finalEvidence, action: i.action || null }, timeoutSeconds: this.c.diagnosisSeconds });
        i.jobSubmitted = true; i.phase = 'diagnosing'; i.job = job;
      } catch { i.dispatchFailed = true; }
    }
    if (i.phase === 'diagnosing') {
      try {
        i.job = await this.io.job(i.id);
        if (['completed', 'failed', 'cancelled'].includes(i.job.status)) i.phase = 'unresolved';
      } catch { i.pollFailed = true; }
    }
    await this.maybeNotify(i, at);
    this.store.save();
  }
  async maybeNotify(i, at) {
    if (this.c.observationOnly || i.notified || (i.phase !== 'unresolved' && at - i.startedAt < this.c.notifySeconds)) return;
    if (i.notifyAttemptAt && at - i.notifyAttemptAt < 30) return;
    i.notifyAttemptAt = at; this.store.save();
    try { await this.io.notify(i, 'unresolved'); i.notified = true; }
    catch { i.notificationFailed = true; }
  }
}
