import { Controller } from './controller.mjs';
import { activeTargets } from './environment.mjs';

// Independent incident state per configured recovery unit. One ECS service is one unit,
// even when its Task contains both Engine and Assistant.
export class Controllers {
  constructor(store, config, io) {
    Object.assign(this, { store, config, io });
    const s = store.value;
    s.scopes ??= {};
    if (s.incident && !s.scopes[s.incident.target]) {
      s.scopes[s.incident.target] = { incident: s.incident, recoveries: s.recoveries || [], history: s.history || [] };
    }
    for (const t of config.targets) {
      s.scopes[t.id] ??= { incident: null, recoveries: (s.recoveries || []).filter(r => r.target === t.id), history: [] };
    }
    this.controllers = new Map(Object.entries(s.scopes).map(([id, value]) => [id, new Controller({ value, save: () => store.save() }, config, io)]));
  }
  async tick(sample, at) {
    const targets = activeTargets(this.config);
    const samples = sample.evidence?.samples || targets.map(t =>
      t.maintenance || this.config.maintenance || sample.status === 'suppressed' ? { target: t.id, status: 'suppressed', code: sample.code || 'maintenance' } :
        { ...sample, target: t.id, diagnosticEligible: false });
    await Promise.all([...this.controllers].map(async ([id, controller]) => {
      const item = targets.some(t => t.id === id) && samples.find(x => x.target === id) || { target: id, status: 'suppressed', code: 'target_disabled' };
      await controller.tick(item, at);
    }));
    const s = this.store.value;
    s.lastTick = at; s.lastSample = sample;
    s.runtimeEnvironment = this.config.runtimeEnvironment;
    s.activeTargets = targets.map(t => t.id);
    s.excludedTargets = this.config.targets.filter(t => !s.activeTargets.includes(t.id)).map(t => t.id);
    s.incidents = Object.values(s.scopes).flatMap(x => x.incident ? [x.incident] : []);
    s.incident = s.incidents[0] || null; // Legacy status clients retain their compact entry point.
    s.recoveries = Object.values(s.scopes).flatMap(x => x.recoveries || []);
    s.history = []; this.store.save();
  }
}
