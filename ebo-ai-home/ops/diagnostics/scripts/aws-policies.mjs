import fs from 'node:fs';
import path from 'node:path';
import { readConfig } from '../src/common.mjs';
import { awsPolicies } from '../src/aws-policy.mjs';
fs.mkdirSync('local/iam', { recursive: true });
for (const t of readConfig().targets.filter(t => t.adapter === 'aws-ecs')) {
  for (const [kind, policy] of Object.entries(awsPolicies(t))) {
    const file = path.join('local/iam', `${t.id}-${kind}.json`);
    fs.writeFileSync(file, JSON.stringify(policy, null, 2));
    console.log(`Prepared ${file}; no AWS permissions were changed.`);
  }
}
