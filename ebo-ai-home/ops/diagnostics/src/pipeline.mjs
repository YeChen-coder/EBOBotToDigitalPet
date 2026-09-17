import { apiTriage, remoteDiagnosis, validateDiagnosis } from './providers.mjs';

export function pipelineConfig(env = process.env) {
  const provider = env.TRIAGE_PROVIDER || 'api';
  const escalation = env.ESCALATION_POLICY || 'on-inconclusive';
  const triageSeconds = Number(env.TRIAGE_TIMEOUT_SECONDS || 90);
  if (!['api', 'codex', 'disabled'].includes(provider) || !['always', 'on-inconclusive'].includes(escalation) ||
      !Number.isInteger(triageSeconds) || triageSeconds < 5 || triageSeconds > 300) throw new Error('Invalid diagnostic pipeline configuration');
  return { provider, escalation, triageSeconds,
    triage: { url: env.TRIAGE_PROVIDER_URL, token: env.TRIAGE_WORKER_TOKEN },
    advanced: { url: env.ADVANCED_PROVIDER_URL, token: env.WORKER_TOKEN } };
}

export async function diagnose(request, signal, config, io = { apiTriage, remoteDiagnosis }) {
  let triage;
  // The job has one overall deadline; a slow first line cannot consume the advanced stage's entire budget.
  const firstSeconds = Math.min(config.triageSeconds, Math.max(1, Math.floor(request.timeoutSeconds / 3)));
  const firstSignal = AbortSignal.any([signal, AbortSignal.timeout(firstSeconds * 1000)]);
  try {
    if (config.provider === 'disabled') triage = { skipped: true, reason: 'disabled' };
    else if (config.provider === 'api') triage = await io.apiTriage(request, firstSignal);
    else triage = await io.remoteDiagnosis({ ...request, id: `${request.id}-triage`, timeoutSeconds: firstSeconds }, firstSignal, config.triage);
    if (!triage.skipped) validateDiagnosis(triage.diagnosis || triage);
  } catch { triage = { failed: true, reason: 'triage_failed_or_timed_out', provider: config.provider }; }
  signal.throwIfAborted();
  const identified = !triage.failed && !triage.skipped && (triage.diagnosis || triage).assessment === 'identified';
  if (identified && config.escalation === 'on-inconclusive') return { triage, advanced: { skipped: true, reason: 'triage_identified' }, recoveryVerified: false };
  const advanced = await io.remoteDiagnosis({ ...request, evidence: { ...request.evidence, triage } }, signal, config.advanced);
  return { triage, advanced, recoveryVerified: false };
}
