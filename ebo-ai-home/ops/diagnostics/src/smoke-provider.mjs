import { randomUUID } from 'node:crypto';
import { remoteDiagnosis } from './providers.mjs';
const id = `smoke-${randomUUID()}`;
const result = await remoteDiagnosis({ id, schemaVersion: 1, timeoutSeconds: 120,
  target: 'synthetic-test', symptom: 'Integration test only; no live fault. Read snapshot.json in /workspace to confirm read-only source access. Report that no real incident was supplied. Do not run other commands.',
  evidence: { synthetic: true, recoveryAttempts: 0, instructionScope: 'read snapshot.json only' },
}, AbortSignal.timeout(125000), { url: 'http://127.0.0.1:8081', token: process.env.DIAGNOSTIC_TOKEN });
console.log(JSON.stringify({ id, result }, null, 2));
