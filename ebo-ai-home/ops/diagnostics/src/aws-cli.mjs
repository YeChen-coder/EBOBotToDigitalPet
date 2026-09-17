import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const exec = promisify(execFile);
const allowed = new Set(['sts get-caller-identity', 'ecs describe-services', 'ecs list-tasks',
  'ecs describe-tasks', 'logs filter-log-events', 'cloudwatch get-metric-statistics', 'ecs stop-task',
  'ecs update-service', 'application-autoscaling describe-scalable-targets']);
export function awsError(error) {
  const text = String(error?.stderr || error?.message || '');
  if (/AccessDenied|UnauthorizedOperation/.test(text)) return 'aws_access_denied';
  if (/ExpiredToken|InvalidClientTokenId|Unable to locate credentials|Token has expired|login|SSO|credentials/i.test(text)) return 'aws_credentials_unavailable';
  if (/Throttl|TooManyRequests/.test(text)) return 'aws_throttled';
  if (/ResourceNotFound|ClusterNotFound|ServiceNotFound/.test(text)) return 'aws_resource_missing';
  return 'aws_collection_failed';
}

// Runs on the host only. No caller can supply executable names, shell commands or AWS options.
export function createAwsCli(connection, target, execute = exec) {
  return async (args, { action = false, control = false, signal } = {}) => {
    const operation = args.slice(0, 2).join(' ');
    if (!allowed.has(operation) || (operation === 'ecs stop-task' && !action) ||
        (operation === 'ecs update-service' && !control)) throw new Error('aws_operation_not_allowed');
    if (operation === 'ecs update-service') {
      const expected = ['ecs', 'update-service', '--cluster', target.aws.cluster, '--service', target.aws.service, '--desired-count'];
      if (args.length !== 8 || expected.some((v, i) => args[i] !== v) || !['0', '1'].includes(args[7])) throw new Error('aws_operation_not_allowed');
    }
    const profile = control ? connection.controlProfile : action ? connection.actionProfile : connection.readProfile;
    if (!profile || (control && !connection.allowRuntimeControl) || (action && !connection.allowTaskReplacement)) throw new Error('aws_action_not_configured');
    const env = { ...process.env };
    // Explicit profiles must not accidentally fall back to unrelated process credentials.
    for (const key of Object.keys(env)) if (key.startsWith('AWS_')) delete env[key];
    Object.assign(env, { AWS_PAGER: '', AWS_CLI_AUTO_PROMPT: 'off', AWS_MAX_ATTEMPTS: '1',
      AWS_CLI_FILE_ENCODING: 'UTF-8', AWS_CLI_OUTPUT_ENCODING: 'UTF-8' });
    for (const [field, key] of [['configFile', 'AWS_CONFIG_FILE'], ['credentialsFile', 'AWS_SHARED_CREDENTIALS_FILE'],
      ['loginCacheDirectory', 'AWS_LOGIN_CACHE_DIRECTORY']]) if (connection[field]) env[key] = connection[field];
    try {
      const { stdout } = await execute(connection.cliPath || 'aws', [...args, '--profile', profile,
        '--region', target.aws.region, '--output', 'json', '--no-cli-pager', '--no-cli-auto-prompt',
        '--cli-connect-timeout', '4', '--cli-read-timeout', '8'],
      { env, signal, timeout: 15000, windowsHide: true, maxBuffer: 2 * 1024 * 1024 });
      return stdout.trim() ? JSON.parse(stdout) : {};
    } catch (error) { throw new Error(awsError(error)); }
  };
}
