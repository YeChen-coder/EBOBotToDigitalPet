// Operator-only setup after authorization. Never imported by the running bridge or model.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { execFileSync } from 'node:child_process';
import { readConfig } from '../src/common.mjs';
import { awsPolicies } from '../src/aws-policy.mjs';

if (!process.argv.includes('--execute')) throw new Error('Use --execute only after authorizing creation of the dedicated IAM reader');
const target = readConfig().targets.find(t => t.id === 'cloud-ebo' && t.adapter === 'aws-ecs');
if (!target) throw new Error('Missing cloud-ebo target');
const hostFile = './local/aws-host.json';
const host = JSON.parse(fs.readFileSync(hostFile, 'utf8').replace(/^\uFEFF/, ''));
const adminFile = './local/aws-provision-admin.json';
if (!fs.existsSync(adminFile)) fs.writeFileSync(adminFile, JSON.stringify(host.connections[target.aws.connection]), { mode: 0o600 });
const admin = JSON.parse(fs.readFileSync(adminFile));
const env = { ...process.env, AWS_CONFIG_FILE: admin.configFile, AWS_SHARED_CREDENTIALS_FILE: admin.credentialsFile,
  AWS_LOGIN_CACHE_DIRECTORY: admin.loginCacheDirectory, AWS_PAGER: '', AWS_CLI_AUTO_PROMPT: 'off', AWS_CLI_FILE_ENCODING: 'UTF-8', AWS_CLI_OUTPUT_ENCODING: 'UTF-8' };
for (const k of ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN']) delete env[k];
function aws(args, missingOkay = false) {
  try {
    return JSON.parse(execFileSync(admin.cliPath, [...args, '--profile', admin.readProfile, '--region', target.aws.region,
      '--output', 'json', '--no-cli-pager', '--no-cli-auto-prompt'], { env, encoding: 'utf8', windowsHide: true, timeout: 30000, stdio: ['ignore', 'pipe', 'pipe'] }) || '{}');
  } catch (e) {
    if (missingOkay && /NoSuchEntity/.test(String(e.stderr))) return null;
    // IAM output, especially access keys, must never appear in exception output.
    throw new Error(`AWS setup failed at ${args.slice(0, 2).join(' ')}; no credential values printed`);
  }
}
const identity = aws(['sts', 'get-caller-identity']);
if (identity.Account !== target.aws.accountId) throw new Error('Unexpected AWS account');
const userName = 'ebo-diagnostics-reader';
const privateDir = path.join(os.homedir(), '.aws', 'ebo-diagnostics');
fs.mkdirSync(privateDir, { recursive: true, mode: 0o700 });
if (process.platform === 'win32') {
  const sid = execFileSync('powershell.exe', ['-NoProfile', '-Command', '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'], { encoding: 'utf8', windowsHide: true }).trim();
  execFileSync('icacls.exe', [privateDir, '/inheritance:r', '/grant:r', `*${sid}:(OI)(CI)F`, '*S-1-5-18:(OI)(CI)F'], { windowsHide: true, stdio: 'pipe' });
}
let user = aws(['iam', 'get-user', '--user-name', userName], true)?.User;
if (!user) user = aws(['iam', 'create-user', '--user-name', userName, '--path', '/ebo-diagnostics/', '--tags', 'Key=ManagedBy,Value=EBO-Diagnostics']).User;
const tags = aws(['iam', 'list-user-tags', '--user-name', userName]).Tags || [];
if (user.Path !== '/ebo-diagnostics/' || !tags.some(t => t.Key === 'ManagedBy' && t.Value === 'EBO-Diagnostics')) throw new Error('Existing IAM user is not owned by this setup');
const policyFile = path.resolve('./local/iam/cloud-ebo-read.json');
fs.mkdirSync(path.dirname(policyFile), { recursive: true });
fs.writeFileSync(policyFile, JSON.stringify(awsPolicies(target).read, null, 2));
aws(['iam', 'put-user-policy', '--user-name', userName, '--policy-name', 'EboDiagnosticsRead', '--policy-document', `file://${policyFile.replaceAll('\\', '/')}`]);
const credentialsFile = path.join(privateDir, 'credentials'); const configFile = path.join(privateDir, 'config');
const keys = aws(['iam', 'list-access-keys', '--user-name', userName]).AccessKeyMetadata || [];
if (!fs.existsSync(credentialsFile)) {
  if (keys.length) throw new Error('IAM key already exists but local credential file is missing; refusing to create another');
  const key = aws(['iam', 'create-access-key', '--user-name', userName]).AccessKey;
  fs.writeFileSync(credentialsFile, `[ebo-diagnostics-read]\naws_access_key_id=${key.AccessKeyId}\naws_secret_access_key=${key.SecretAccessKey}\n`, { mode: 0o600, flag: 'wx' });
}
fs.writeFileSync(configFile, `[profile ebo-diagnostics-read]\nregion=${target.aws.region}\noutput=json\n`, { mode: 0o600 });
host.connections[target.aws.connection] = { ...host.connections[target.aws.connection], cliPath: admin.cliPath,
  readProfile: 'ebo-diagnostics-read', configFile, credentialsFile };
fs.writeFileSync(hostFile, JSON.stringify(host, null, 2));
fs.writeFileSync('./local/iam/reader-installation.json', JSON.stringify({ userName, arn: user.Arn,
  installedAt: new Date().toISOString(), credentialsDirectory: privateDir, permission: 'read-only' }, null, 2));
console.log(JSON.stringify({ userName, arn: user.Arn, profile: 'ebo-diagnostics-read', permission: 'read-only', credentialsDirectory: privateDir }));
