export function workerConfig(env = process.env) {
  const stage = env.CODEX_STAGE || 'advanced';
  const model = env.CODEX_MODEL || (stage === 'triage' ? 'gpt-5.6-luna' : 'gpt-5.6-sol');
  const effort = env.CODEX_REASONING_EFFORT || (stage === 'triage' ? 'low' : 'high');
  const maxSeconds = Number(env.CODEX_MAX_SECONDS || (stage === 'triage' ? 90 : 300));
  if (!['triage', 'advanced'].includes(stage) || !/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,99}$/.test(model) ||
      !['minimal', 'low', 'medium', 'high', 'xhigh', 'max'].includes(effort) ||
      !Number.isInteger(maxSeconds) || maxSeconds < 5 || maxSeconds > 600) throw new Error('Invalid Codex worker configuration');
  return { stage, model, effort, maxSeconds };
}
