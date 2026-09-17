import path from 'node:path';
import fs from 'node:fs';
import { Codex } from '@openai/codex-sdk';
import { Store, required, serve, audit } from './common.mjs';
import { Jobs } from './jobs.mjs';
import { diagnosisSchema, instructions, validateDiagnosis } from './providers.mjs';
import { workerConfig } from './worker-config.mjs';

const token = required('WORKER_TOKEN');
const settings = workerConfig();
const home = process.env.CODEX_HOME || '/home/node/.codex';
const credentialReady = () => Boolean(process.env.CODEX_API_KEY || fs.existsSync(path.join(home, 'auth.json')));
// Only provider credentials reach the CLI. The API server's WORKER_TOKEN is not inherited.
const env = Object.fromEntries(['PATH', 'HOME', 'TMPDIR', 'CODEX_HOME', 'CODEX_API_KEY',
  'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
  'SSL_CERT_FILE', 'SSL_CERT_DIR'].filter(k => process.env[k]).map(k => [k, process.env[k]]));
const codex = new Codex({ env,
  // Pinned SDK's official compatibility backend: preserves read-only + seccomp networking
  // without granting nested user namespaces or adding container capabilities.
  config: { features: { use_legacy_landlock: process.env.CODEX_LEGACY_LANDLOCK !== 'false' } },
  ...(process.env.CODEX_API_KEY ? { apiKey: process.env.CODEX_API_KEY } : {}) });
const jobs = new Jobs(new Store(path.join(process.env.DATA_DIR || './data/worker', 'jobs.json'), { jobs: {} }), async (request, signal) => {
  if (!credentialReady()) throw new Error('credentials_not_configured');
  const thread = codex.startThread({
    workingDirectory: process.env.SOURCE_DIR || '/workspace', skipGitRepoCheck: true,
    sandboxMode: 'read-only', approvalPolicy: 'never', networkAccessEnabled: false, webSearchMode: 'disabled',
    model: settings.model, modelReasoningEffort: settings.effort,
  });
  const stageInstructions = settings.stage === 'triage' ? 'First-line triage: inspect the supplied evidence and only narrowly relevant source. Keep the report concise. If evidence is insufficient, return inconclusive so the advanced investigator can continue.' : 'Advanced investigation: examine the prior triage, verify its claims against evidence and relevant source, and explain unresolved alternatives.';
  const result = await thread.run(`${instructions}\n${stageInstructions}\nSource snapshot is in the current directory.\nIncident evidence:\n${JSON.stringify(request)}`, { outputSchema: diagnosisSchema, signal });
  const commands = result.items.filter(x => x.type === 'command_execution');
  return { provider: 'codex-sdk', stage: settings.stage, model: settings.model, reasoningEffort: settings.effort,
    threadId: thread.id, diagnosis: validateDiagnosis(JSON.parse(result.finalResponse)), usage: result.usage,
    tools: { succeeded: commands.filter(x => x.exit_code === 0).length, failed: commands.filter(x => x.exit_code !== 0).length } };
}, { maxSeconds: settings.maxSeconds });
serve({ port: Number(process.env.PORT || 8082), token, route: (...args) => jobs.route(...args),
  health: () => ({ ok: true, provider: 'codex-sdk', ...settings, credentialConfigured: credentialReady() }),
});
audit('codex_worker_started', { credentialConfigured: credentialReady() });
