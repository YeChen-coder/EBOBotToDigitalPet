import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
// Inherit stdio for the native sandbox launcher; payload asserts all three boundaries.
execFileSync(process.execPath, ['node_modules/@openai/codex/bin/codex.js',
  '--enable', 'use_legacy_landlock',
  'sandbox', '--', process.execPath, path.join(path.dirname(fileURLToPath(import.meta.url)), 'sandbox-payload.mjs')], { timeout: 10000, stdio: 'inherit' });
