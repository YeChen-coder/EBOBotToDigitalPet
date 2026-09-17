import { jsonFetch } from './common.mjs';
import { activeTargets } from './environment.mjs';

const fields = ['ok', 'uptime_seconds', 'realtime_connected', 'video_streaming', 'audio_streaming',
  'last_frame_age_seconds', 'last_audio_age_seconds', 'transport_media_ok', 'source_audio_ok',
  'media_starting', 'media_recovery_attempts', 'last_media_recovery_at', 'unplanned_realtime_reconnects'];
const sourceStatuses = new Set(['receiving', 'muted', 'disabled', 'disconnected', 'no_source_packets',
  'no_decoded_pcm', 'source_stale', 'monitor_stale', 'monitor_error', 'not_monitored']);
export function healthEvidence(h) {
  const data = Object.fromEntries(fields.filter(k => typeof h[k] === 'boolean' || (typeof h[k] === 'number' && Number.isFinite(h[k]))).map(k => [k, h[k]]));
  data.source_audio_status = sourceStatuses.has(h.source_audio_status) ? h.source_audio_status : 'unknown';
  return data;
}
export function classifyHealth(h, target, config) {
  const evidence = healthEvidence(h);
  const result = (status, code, recoverable = false) => ({ status, code, target: target.id, recoverable, evidence });
  // Require the contract even for a nominal `ok: true`; stale/old Engine data is not a pass.
  if (typeof h.ok !== 'boolean' || typeof h.realtime_connected !== 'boolean' || typeof h.video_streaming !== 'boolean') return result('fault', 'health_contract_invalid');
  if (h.media_starting === true && h.uptime_seconds < config.startupSeconds) return result('grace', 'starting');
  const intentional = ['muted', 'disabled'].includes(h.source_audio_status);
  if (!h.realtime_connected) return result('fault', 'realtime_disconnected', !intentional && target.restartOnStall === true);
  if (!h.video_streaming) return result('fault', 'video_stalled', !intentional && target.restartOnStall === true);
  if (intentional) return result('suppressed', 'audio_intentionally_disabled');
  if (h.source_audio_status !== 'receiving' || h.source_audio_ok !== true) return result('fault', 'source_audio_unconfirmed');
  if (h.audio_streaming !== true) return result('fault', 'audio_transport_stalled', target.restartOnStall === true);
  if (h.ok !== true) return result('fault', 'health_inconsistent');
  return result('healthy', 'healthy');
}

export async function observe(config, bridge, fetchJson = jsonFetch) {
  if (config.maintenance) return { status: 'suppressed', code: 'maintenance', evidence: {} };
  let snapshot;
  try { snapshot = await bridge.snapshot(); }
  catch { return { status: 'fault', target: 'infrastructure', code: 'host_bridge_unavailable', recoverable: false, evidence: {} }; }
  // The authenticated host owns live intent; mounted startup config is only a fallback.
  if (snapshot.runtime?.controlVersion === 1 && ['aws', 'local', 'stopped'].includes(snapshot.runtime.desired)) {
    config.runtimeEnvironment = snapshot.runtime.desired;
    if (snapshot.runtime.monitoringSuppressed) return { status: 'suppressed', code: config.runtimeEnvironment === 'stopped' ? 'project_stopped' : 'runtime_transition', evidence: { runtime: snapshot.runtime } };
  }
  if (snapshot.runtimeEnvironment && snapshot.runtimeEnvironment !== config.runtimeEnvironment)
    return { status: 'fault', code: 'runtime_environment_mismatch', diagnosticEligible: false, evidence: {} };
  const states = snapshot.targets || {};
  const samples = await Promise.all(activeTargets(config).map(async t => {
    const base = { target: t.id, recoverable: false, evidence: { container: states[t.id] || { status: 'missing' } } };
    if (t.maintenance) return { ...base, status: 'suppressed', code: 'target_maintenance' };
    const state = states[t.id];
    if (t.adapter === 'aws-ecs') {
      if (!state?.observation) return { ...base, status: 'fault', code: 'aws_snapshot_unavailable', diagnosticEligible: false };
      const { observation, ...cloud } = state;
      return { ...base, ...observation, target: t.id, evidence: { cloud } };
    }
    if (!snapshot.dockerOk) return { ...base, status: 'fault', code: 'docker_unavailable', diagnosticEligible: false };
    if (!state || state.status === 'missing') return { ...base, status: 'fault', code: 'container_missing' };
    // Docker pause is an explicit control-plane state; it is not a process crash.
    // Resume monitoring automatically after unpause, without leaving a maintenance flag behind.
    if (state.status === 'paused') return { ...base, status: 'suppressed', code: 'container_paused' };
    // Exit 0 proves a clean exit, not operator intent. Only explicit maintenance suppresses it.
    if (state.status === 'exited' && state.exitCode === 0 && !state.oomKilled) return { ...base, status: 'fault', code: 'container_stopped_unexpected' };
    if (state.status !== 'running') return { ...base, status: 'fault', code: 'container_not_running' };
    if (state.ageSeconds < config.startupSeconds) return { ...base, status: 'grace', code: 'starting' };
    if (state.health === 'unhealthy') return { ...base, status: 'fault', code: 'container_unhealthy' };
    if (t.probe === 'container') return { ...base, status: 'healthy', code: 'process_running' };
    try {
      if (t.probe === 'http') {
        const r = await fetch(t.url, { signal: AbortSignal.timeout(4000), redirect: 'manual' });
        await r.body?.cancel();
        return { ...base, status: r.status >= 200 && r.status < 400 ? 'healthy' : 'fault', code: r.status >= 200 && r.status < 400 ? 'http_ready' : 'http_failed', recoverable: false };
      }
      const h = classifyHealth(await fetchJson(t.url), t, config);
      return { ...h, evidence: { ...base.evidence, health: h.evidence } };
    } catch {
      // Without microphone/desired-state evidence, do not restart the Engine or Assistant blindly.
      return { ...base, status: 'fault', code: 'probe_unreachable' };
    }
  }));
  // Parent faults win over cascading symptoms. Target order is the configured dependency order.
  const fault = samples.find(s => s.status === 'fault');
  if (fault) return { ...fault, evidence: { samples } };
  if (samples.some(s => s.status === 'grace')) return { status: 'grace', code: 'starting', evidence: { samples } };
  if (!samples.length || samples.some(s => s.status === 'suppressed')) return { status: 'suppressed', code: 'capability_disabled', evidence: { samples } };
  return { status: 'healthy', code: 'healthy', evidence: { samples } };
}
