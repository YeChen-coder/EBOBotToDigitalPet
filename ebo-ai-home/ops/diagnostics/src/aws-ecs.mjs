import { now } from './common.mjs';
import { classifyAws, safeCloudHealth } from './aws-health.mjs';
import { diagnosticEvents } from './telemetry.mjs';

const seconds = v => typeof v === 'number' ? v : Date.parse(v) / 1000;
const boundedReason = value => {
  const text = String(value || '');
  for (const [code, pattern] of [['capacity_unavailable', /insufficient|capacity is unavailable/i],
    ['task_role_failure', /unable to assume|access.?denied/i], ['image_pull_failed', /CannotPullContainer|pull.*image/i],
    ['resource_initialization_failed', /ResourceInitializationError/], ['task_placement_failed', /unable to place|unable to start/i],
    ['steady_state', /steady state/i]]) if (pattern.test(text)) return code;
  return ['OutOfMemoryError', 'EssentialContainerExited', 'TaskFailedToStart', 'UserInitiated',
    'ServiceSchedulerInitiated', 'SpotInterruption', 'TerminationNotice'].find(x => text.includes(x)) ||
    diagnosticEvents(text)[0]?.event || (text ? 'other_reason' : null);
};
function safeTask(t) {
  return { taskArn: t.taskArn, taskDefinitionArn: t.taskDefinitionArn, status: t.lastStatus, desiredStatus: t.desiredStatus,
    health: t.healthStatus || 'UNKNOWN', startedAt: seconds(t.startedAt), stoppedAt: seconds(t.stoppedAt),
    stopCode: boundedReason(t.stopCode), reason: boundedReason(t.stoppedReason),
    containers: (t.containers || []).map(c => ({ name: c.name, imageDigest: c.imageDigest, status: c.lastStatus,
      health: c.healthStatus || 'UNKNOWN', exitCode: c.exitCode, reason: boundedReason(c.reason) })) };
}

export class AwsEcsAdapter {
  constructor(target, config, connection, store, call, clock = now) {
    Object.assign(this, { target, config, connection, store, call, clock });
    this.inflight = null; this.nextPoll = 0; this.lastError = null;
  }
  snapshot() {
    const state = this.store.value.snapshot;
    if (!state && !this.lastError) return { observation: { status: 'grace', code: 'aws_initial_collection', target: this.target.id }, provider: 'aws-ecs' };
    const safe = { ...(state || {}), ...(this.lastError ? { error: this.lastError } : {}) };
    return { ...safe, provider: 'aws-ecs', observation: classifyAws(safe, this.target, this.config, this.clock()) };
  }
  refresh(force = false) {
    if (this.inflight) return this.inflight;
    if (!force && this.clock() < this.nextPoll) return Promise.resolve();
    this.nextPoll = this.clock() + this.target.aws.pollSeconds;
    this.inflight = this.collect().then(state => {
      this.lastError = null; this.store.value.snapshot = state; this.store.save();
    }).catch(error => {
      this.lastError = /^aws_[a-z_]+$/.test(error.message) ? error.message : 'aws_collection_failed';
    }).finally(() => { this.inflight = null; });
    return this.inflight;
  }
  async identity(action, signal) {
    const id = await this.call(['sts', 'get-caller-identity'], { action, signal });
    if (id.Account !== this.target.aws.accountId) throw new Error('aws_account_mismatch');
    if (id.Arn?.endsWith(':root') && (action || !this.connection.allowRootReadOnce)) throw new Error('aws_root_identity_refused');
    return id;
  }
  async serviceTasks(signal, action = false) {
    const a = this.target.aws; const options = { signal, action };
    const response = await this.call(['ecs', 'describe-services', '--cluster', a.cluster, '--services', a.service], options);
    if (response.failures?.length) throw new Error('aws_service_missing');
    const service = response.services?.[0];
    if (!service) throw new Error('aws_service_missing');
    const listed = await this.call(['ecs', 'list-tasks', '--cluster', a.cluster, '--service-name', a.service, '--no-paginate', '--max-results', '10'], options);
    if (listed.nextToken) throw new Error('aws_task_limit_exceeded');
    const tasks = listed.taskArns?.length ? await this.call(['ecs', 'describe-tasks', '--cluster', a.cluster, '--tasks', ...listed.taskArns], options) : { tasks: [] };
    if (tasks.failures?.length) throw new Error('aws_task_snapshot_incomplete');
    return { service, tasks: tasks.tasks || [] };
  }
  async logs(c, taskArn, signal, filter) {
    const a = this.target.aws; const end = this.clock() * 1000; let token; const events = [];
    for (let page = 0; page < a.maxLogPages; page++) {
      const args = ['logs', 'filter-log-events', '--log-group-name', c.logGroup,
        '--log-stream-names', `${c.streamPrefix}/${taskArn.split('/').at(-1)}`,
        '--start-time', String(Math.floor(end - a.logWindowSeconds * 1000)), '--end-time', String(Math.floor(end)),
        '--limit', '200', '--no-paginate'];
      if (filter) args.push('--filter-pattern', filter);
      if (token) args.push('--next-token', token);
      const r = await this.call(args, { signal });
      events.push(...(r.events || []));
      if (!r.nextToken || r.nextToken === token) return { events, truncated: false };
      token = r.nextToken;
    }
    return { events, truncated: true };
  }
  async collect() {
    const signal = AbortSignal.timeout(45000); const at = this.clock(); const a = this.target.aws;
    await this.identity(false, signal);
    const { service, tasks } = await this.serviceTasks(signal);
    const s = this.store.value;
    const current = tasks.filter(t => t.lastStatus !== 'STOPPED');
    s.seenTasks = (s.seenTasks || []).filter(x => at - x.at < this.config.repeatWindowSeconds);
    for (const t of current) if (!s.seenTasks.some(x => x.id === t.taskArn)) s.seenTasks.push({ id: t.taskArn, at });
    const deploying = service.deployments?.some(d => d.rolloutState === 'IN_PROGRESS') === true;
    const unready = deploying || service.pendingCount > 0 || current.length !== 1 || current.some(t =>
      t.lastStatus !== 'RUNNING' || t.healthStatus !== 'HEALTHY' || a.containers.some(c =>
        !t.containers?.some(x => x.name === c.name && x.lastStatus === 'RUNNING' && x.healthStatus === 'HEALTHY')));
    if (unready) s.transitionSince ??= at; else s.transitionSince = null;
    const health = {}; const collectionErrors = [];
    if (current.length === 1) await Promise.all(a.containers.filter(c => c.probe !== 'container').map(async c => {
      try {
        const result = await this.logs(c, current[0].taskArn, signal, '{ $.event = "health.snapshot" }');
        if (result.truncated) { collectionErrors.push({ container: c.name, error: 'health_page_limit' }); return; }
        const rows = result.events.flatMap(e => {
          try {
            const row = JSON.parse(e.message); const eventAt = seconds(row.timestamp);
            if (row.event !== 'health.snapshot' || row.service !== c.name || row.schema_version !== 1 || !Number.isFinite(eventAt)) return [];
            return [{ at: Math.min(e.timestamp / 1000, eventAt), taskArn: current[0].taskArn, health: safeCloudHealth(row.health, c.probe) }];
          } catch { return []; }
        }).sort((x, y) => x.at - y.at);
        health[c.name] = rows.at(-1) || null;
      } catch (e) { collectionErrors.push({ container: c.name, error: /^aws_[a-z_]+$/.test(e.message) ? e.message : 'aws_logs_failed' }); }
    }));
    return { observedAt: at, accountId: a.accountId, region: a.region, cluster: a.cluster,
      service: { name: a.service, desiredCount: service.desiredCount, runningCount: service.runningCount,
        pendingCount: service.pendingCount, deploying, status: service.status },
      serviceEvents: (service.events || []).slice(0, 5).map(e => ({ at: seconds(e.createdAt), category: boundedReason(e.message) })),
      tasks: current.map(safeTask), health, collectionErrors, transitionSince: s.transitionSince ?? at,
      replacementCount: Math.max(0, s.seenTasks.length - 1),
      canReplace: this.connection.allowTaskReplacement === true && !!this.connection.actionProfile &&
        service.deploymentConfiguration?.maximumPercent === 100 && service.deploymentConfiguration?.minimumHealthyPercent === 0 };
  }
  async evidence() {
    const signal = AbortSignal.timeout(45000); const a = this.target.aws;
    await this.refresh(true);
    if (this.lastError) return { ...this.snapshot(), evidenceErrors: [this.lastError] };
    const state = this.snapshot(); const events = []; const evidenceErrors = [];
    await Promise.all(a.containers.map(async c => {
      const task = state.tasks?.[0]; if (!task) return;
      try {
        const r = await this.logs(c, task.taskArn, signal);
        if (r.truncated) evidenceErrors.push({ container: c.name, error: 'log_page_limit' });
        for (const e of r.events) for (const event of diagnosticEvents(e.message)) events.push({ ...event, at: e.timestamp / 1000, container: c.name });
      } catch { evidenceErrors.push({ container: c.name, error: 'logs_unavailable' }); }
    }));
    const metrics = await Promise.all(['CPUUtilization', 'MemoryUtilization'].map(async metric => {
      try {
        const r = await this.call(['cloudwatch', 'get-metric-statistics', '--namespace', 'AWS/ECS', '--metric-name', metric,
          '--dimensions', `Name=ClusterName,Value=${a.cluster}`, `Name=ServiceName,Value=${a.service}`,
          '--start-time', new Date((this.clock() - a.logWindowSeconds) * 1000).toISOString(),
          '--end-time', new Date(this.clock() * 1000).toISOString(), '--period', '60', '--statistics', 'Average', 'Maximum'], { signal });
        return { metric, points: (r.Datapoints || []).map(x => ({ at: seconds(x.Timestamp), average: x.Average, max: x.Maximum })).sort((x, y) => x.at - y.at).slice(-60) };
      } catch { return { metric, unavailable: true }; }
    }));
    let stopped = [];
    try {
      const r = await this.call(['ecs', 'list-tasks', '--cluster', a.cluster, '--service-name', a.service,
        '--desired-status', 'STOPPED', '--max-results', '10', '--no-paginate'], { signal });
      if (r.taskArns?.length) stopped = (await this.call(['ecs', 'describe-tasks', '--cluster', a.cluster, '--tasks', ...r.taskArns.slice(0, 10)], { signal })).tasks.map(safeTask);
    } catch { evidenceErrors.push({ error: 'stopped_tasks_unavailable' }); }
    return { ...state, events: events.slice(-80), metrics, stopped, evidenceErrors,
      scope: 'bounded_window_categories_and_allowlisted_health_only', sourceContext: 'Cloud deployment can differ from the local code snapshot. Verify revision before citing source.' };
  }
  async prepareRestart() {
    await this.refresh(true);
    const state = this.snapshot();
    if (state.observation.status !== 'fault' || !state.observation.recoverable || state.tasks.length !== 1) throw new Error('aws_recovery_not_applicable');
    return { taskArn: state.tasks[0].taskArn };
  }
  async restart(expected) {
    const signal = AbortSignal.timeout(45000); const a = this.target.aws;
    await this.identity(true, signal);
    const { service, tasks } = await this.serviceTasks(signal, true);
    const d = service.deploymentConfiguration;
    if (tasks.length !== 1 || tasks[0].taskArn !== expected.taskArn || tasks[0].lastStatus !== 'RUNNING' ||
        tasks[0].desiredStatus !== 'RUNNING' || service.desiredCount !== 1 || service.pendingCount !== 0 ||
        service.deployments?.some(x => x.rolloutState === 'IN_PROGRESS') || d?.maximumPercent !== 100 || d?.minimumHealthyPercent !== 0) throw new Error('aws_recovery_precondition_changed');
    // Stop only the exact observed task; ECS owns replacement. Never change desiredCount or run a second Engine.
    await this.call(['ecs', 'stop-task', '--cluster', a.cluster, '--task', expected.taskArn,
      '--reason', 'EBO deterministic recovery: confirmed application stall'], { action: true, signal });
    this.nextPoll = 0;
  }
}
