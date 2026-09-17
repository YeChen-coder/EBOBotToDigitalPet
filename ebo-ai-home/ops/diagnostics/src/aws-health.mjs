import { classifyHealth, healthEvidence } from './probes.mjs';

export function safeCloudHealth(h, probe) {
  if (probe === 'ebo-health') return healthEvidence(h || {});
  if (probe === 'engine-health') return { robot_count: Number.isInteger(h?.robot_count) ? h.robot_count : null };
  return {};
}

// Control-plane failure and stale telemetry are monitoring failures, not proof of an application crash.
export function classifyAws(state, target, config, at) {
  const a = target.aws;
  const result = (status, code, extra = {}) => ({ status, code, target: target.id, recoverable: false, ...extra });
  if (state.error) return result('fault', state.error, { diagnosticEligible: false });
  if (!state.observedAt || at - state.observedAt > a.snapshotMaxAgeSeconds) return result('fault', 'aws_snapshot_stale', { diagnosticEligible: false });
  if (state.service?.desiredCount === 0) return result('suppressed', 'aws_service_scaled_to_zero');
  if (!state.service) return result('fault', 'aws_service_missing');
  if (state.service.desiredCount !== 1 || state.tasks.length > 1) return result('fault', 'aws_single_input_overlap');
  if (state.replacementCount >= 3) return result('fault', 'aws_task_replacement_storm');
  const task = state.tasks[0];
  const ecsUnready = !task || task.status !== 'RUNNING' || task.health !== 'HEALTHY' ||
    a.containers.some(c => !task.containers.some(x => x.name === c.name && x.status === 'RUNNING' && x.health === 'HEALTHY'));
  if (state.service.deploying || state.service.pendingCount > 0 || ecsUnready) {
    return at - state.transitionSince < a.selfHealingSeconds ? result('grace', 'aws_scheduler_recovering') : result('fault', 'aws_scheduler_recovery_failed');
  }
  for (const c of a.containers) {
    if (c.probe === 'container') continue;
    const h = state.health[c.name];
    if (!h || h.taskArn !== task.taskArn || at - h.at > a.healthMaxAgeSeconds || h.at > at + 30) {
      return result('fault', 'aws_health_telemetry_stale', { diagnosticEligible: false });
    }
    if (c.probe === 'engine-health') {
      if (!(h.health.robot_count > 0)) return result('fault', 'aws_engine_no_robot');
      continue;
    }
    const sample = classifyHealth(h.health, target, config);
    if (sample.status !== 'healthy') return { ...sample, code: `aws_${sample.code}`,
      recoverable: sample.recoverable && state.canReplace === true, recoverySeconds: a.recoverySeconds };
  }
  return result('healthy', 'aws_business_healthy');
}
