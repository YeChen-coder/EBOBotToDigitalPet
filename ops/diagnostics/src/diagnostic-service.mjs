import path from 'node:path';
import { Store, required, serve, audit } from './common.mjs';
import { Jobs } from './jobs.mjs';
import { diagnose, pipelineConfig } from './pipeline.mjs';

const token = required('DIAGNOSTIC_TOKEN');
const config = pipelineConfig();
required('WORKER_TOKEN');
if (config.provider === 'codex') required('TRIAGE_WORKER_TOKEN');
const jobs = new Jobs(new Store(path.join(process.env.DATA_DIR || './data/diagnostic', 'jobs.json'), { jobs: {} }),
  (request, signal) => diagnose(request, signal, config));
serve({ port: Number(process.env.PORT || 8081), token, route: (...args) => jobs.route(...args),
  health: () => ({ ok: true, triageProvider: config.provider, escalationPolicy: config.escalation }) });
audit('diagnostic_service_started');
