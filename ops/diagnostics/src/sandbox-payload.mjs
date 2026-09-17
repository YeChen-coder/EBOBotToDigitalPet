import fs from 'node:fs';
const report = { read: false, writeBlocked: false, networkBlocked: false };
report.read = JSON.parse(fs.readFileSync('/workspace/snapshot.json')).files.length > 0;
try { fs.writeFileSync('/data/sandbox-probe', 'test'); } catch { report.writeBlocked = true; }
try { await fetch('http://127.0.0.1:8082/health', { signal: AbortSignal.timeout(2000) }); } catch { report.networkBlocked = true; }
console.log(JSON.stringify(report));
if (!Object.values(report).every(Boolean)) process.exit(1);
