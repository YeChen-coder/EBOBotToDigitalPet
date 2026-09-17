import { now } from './common.mjs';

export const runtimeModes = ['aws', 'local', 'stopped'];
export const modeLabels = { aws: '云端运行', local: '本地运行', stopped: '全部停止' };
export const runtimeErrors = {
  aws_action_not_configured: '尚未配置云端启停权限。请配置独立的 controlProfile 和 allowRuntimeControl。',
  aws_access_denied: 'AWS 拒绝了启停操作；控制身份需要指定 ECS 服务的 UpdateService 权限。',
  aws_credentials_unavailable: 'AWS 登录已过期或不可用；请在本机重新登录后重试。',
  aws_autoscaling_enabled: '此服务仍有自动扩缩容规则，可能自行重新启动。请先停用这些规则后重试。',
  aws_account_mismatch: 'AWS 账号与此项目配置不一致，已拒绝操作。',
  aws_root_identity_refused: '不能使用 AWS root 身份控制服务，请使用项目专用身份。',
  aws_service_missing: '找不到配置的 ECS 服务，请检查云端目标。',
  aws_collection_failed: '无法完整读取 AWS 状态；当前不能确认云端是否已停止。请检查网络和 AWS 连接。',
  aws_throttled: 'AWS 暂时限制请求速率，请稍后重试。',
  aws_task_limit_exceeded: '任务列表超过核验上限；无法证明所有任务已停止，请检查 ECS 服务任务。',
  aws_task_snapshot_incomplete: 'AWS 返回的任务状态不完整，暂时不能确认停止成功。',
  aws_not_fargate: '目标不是已确认的 Fargate 服务，已拒绝更改。',
  aws_stop_unverified: '云端尚未确认完全停止。不会启动本地，请稍后重试。',
  local_stop_unverified: '本地容器尚未确认全部停止。不会启动云端，请检查 Docker 后重试。',
  docker_unavailable: '无法连接 Docker，不能确认本地容器已停止。请启动 Docker Desktop 后重试。',
  runtime_health_timeout: '服务已发出启动请求，但功能健康检查尚未通过；请查看实际状态和诊断记录。',
  runtime_interrupted: '上一次切换被宿主机重启打断。请点击目标模式重新核验并继续。',
  runtime_stop_requested: '已收到全部停止请求，正在结束前一个操作。',
  runtime_operation_failed: '操作未完成；已保留目标选择和步骤，请检查本地 Docker / AWS 连接后重试。',
};

// One host-owned durable intent. Never infer intent from a crashed/stopped container.
export class RuntimeControl {
  constructor(store, config, io, clock = now) {
    Object.assign(this, { store, config, io, clock });
    this.busy = false; this.repairCount = 0; this.actual = null;
    const s = store.value;
    s.desired ??= config.runtimeEnvironment;
    if (!runtimeModes.includes(s.desired)) throw new Error('invalid_saved_runtime');
    s.phase ??= 'unmanaged'; s.history ??= [];
    if (s.queuedMode === 'stopped') { s.desired = 'stopped'; delete s.queuedMode; s.phase = 'switching'; }
    if (s.phase === 'switching') { s.phase = 'failed'; s.error = 'runtime_interrupted'; store.save(); }
    this.sync();
  }
  sync() { this.config.runtimeEnvironment = this.store.value.desired; }
  status() {
    const s = this.store.value;
    return { ...s, desired: s.queuedMode || s.desired, controlVersion: 1, busy: this.busy || this.repairCount > 0, actual: this.actual, message: runtimeErrors[s.error] || null,
      monitoringSuppressed: !!s.queuedMode || s.phase === 'switching' || (s.phase === 'failed' && s.error !== 'runtime_health_timeout') || s.desired === 'stopped' };
  }
  async observe() {
    if (!this.observing) this.observing = this.io.inspect().then(actual => { this.actual = actual; return actual; }).finally(() => { this.observing = null; });
    return this.observing;
  }
  async repair(fn) {
    if (this.busy || this.status().monitoringSuppressed) throw new Error('runtime_busy');
    this.repairCount++;
    try { return await fn(); } finally { this.repairCount--; this.drainStop(); }
  }
  drainStop() {
    if (!this.busy && !this.repairCount && this.store.value.queuedMode === 'stopped') {
      delete this.store.value.queuedMode;
      this.request('stopped');
    }
  }
  request(desired, source = 'user') {
    if (!runtimeModes.includes(desired)) return { code: 400, body: { error: 'invalid_mode' } };
    if (desired === 'stopped' && (this.busy || this.repairCount)) {
      if (this.store.value.desired !== 'stopped') {
        this.store.value.queuedMode = 'stopped'; this.config.runtimeEnvironment = 'stopped'; this.store.save();
      }
      return { code: 202, body: this.status() };
    }
    if (this.busy || this.repairCount) return { code: 409, body: { error: 'runtime_busy', message: '另一个切换或恢复正在结束，请稍后重试。' } };
    this.busy = true;
    Object.assign(this.store.value, { desired, phase: 'switching', source, step: '准备切换', error: null, requestedAt: this.clock(), steps: [], healthChecks: [] });
    this.sync(); this.store.save(); // Intent is durable before any side effect.
    this.pending = this.apply().finally(() => { this.busy = false; this.drainStop(); });
    return { code: 202, body: this.status() };
  }
  async step(label, fn) {
    const s = this.store.value;
    if (s.queuedMode) throw new Error('runtime_stop_requested');
    s.step = label; s.steps.push({ label, at: this.clock(), status: 'running' }); this.store.save();
    await fn(); s.steps.at(-1).status = 'completed'; this.store.save();
    if (s.queuedMode) throw new Error('runtime_stop_requested');
    await this.observe().catch(() => {});
  }
  async apply() {
    const s = this.store.value;
    const health = checks => { if(s.queuedMode) throw new Error('runtime_stop_requested'); s.healthChecks = checks; this.store.save(); };
    try {
      if (s.desired === 'stopped') {
        // Both stops must be attempted even if one side is unreachable.
        const errors = [];
        for (const [label, fn] of [['停止本地三个容器', () => this.io.stopLocal()], ['云端任务数归零并等待停止', () => this.io.stopCloud()]]) {
          try { await this.step(label, fn); } catch (e) { s.steps.at(-1).status = 'failed'; errors.push(e); }
        }
        if (errors.length) throw errors[0];
      } else if (s.desired === 'aws') {
        await this.step('停止本地三个容器并关闭自动重启', () => this.io.stopLocal());
        await this.step('启动云端 Fargate 服务', () => this.io.startCloud());
        await this.step('确认云端任务和音视频功能健康', () => this.io.waitHealthy('aws', health));
      } else {
        await this.step('云端任务数归零并确认停止', () => this.io.stopCloud());
        await this.step('启动本地三个容器', () => this.io.startLocal());
        await this.step('确认 Home Assistant、Engine 和 Assistant 健康', () => this.io.waitHealthy('local', health));
      }
      await this.observe();
      if (!this.io.matches(s.desired, this.actual)) {
        if (s.desired !== 'local' && !this.actual?.local?.stopped) throw new Error('local_stop_unverified');
        if (s.desired !== 'aws' && !this.actual?.cloud?.stopped) throw new Error('aws_stop_unverified');
        throw new Error('runtime_health_timeout');
      }
      s.phase = 'ready'; s.step = '目标状态已确认'; s.verifiedAt = this.clock();
    } catch (e) {
      s.phase = 'failed'; s.error = Object.hasOwn(runtimeErrors, e.message) ? e.message : 'runtime_operation_failed';
      if (s.steps.at(-1)?.status === 'running') s.steps.at(-1).status = 'failed';
      await this.observe().catch(() => { this.actual = null; });
    } finally {
      s.finishedAt = this.clock();
      s.history = [...s.history, { desired: s.desired, phase: s.phase, source: s.source, error: s.error, at: s.finishedAt, steps: structuredClone(s.steps) }].slice(-40);
      this.store.save();
    }
  }
  async poll() {
    await this.observe();
    if (this.busy || this.repairCount) return;
    this.busy = true; let restore = false;
    try {
      const s = this.store.value;
      // Keep intentional shutdown effective if an external tool starts the inactive side.
      // Importing old monitor configuration alone never authorizes a first lifecycle operation.
      if (s.phase !== 'unmanaged') {
        const failures = []; let changed = false;
        if (s.desired !== 'local' && this.actual.local?.stopped === false) {
          try { await this.io.stopLocal(); changed = true; } catch (e) { failures.push(e); }
        }
        if (s.desired !== 'aws' && this.actual.cloud?.stopped === false) {
          try { await this.io.stopCloud(); changed = true; } catch (e) { failures.push(e); }
        }
        if (failures.length) { s.phase = 'failed'; s.error = Object.hasOwn(runtimeErrors, failures[0].message) ? failures[0].message : 'runtime_operation_failed'; this.store.save(); }
        if (changed) await this.observe();
        const activeStopped = s.desired === 'local' ? this.actual.local?.known && this.actual.local.containers.some(c => ['exited', 'created', 'missing', 'dead'].includes(c.status)) :
          s.desired === 'aws' && this.actual.cloud?.known && this.actual.cloud.services.some(c => c.desiredCount === 0);
        const targetMaintenance = this.config.targets.some(t => t.maintenance && (s.desired === 'aws' ? t.adapter === 'aws-ecs' : t.adapter !== 'aws-ecs'));
        if (s.phase === 'ready' && activeStopped && this.config.autoRecovery && !this.config.maintenance && !targetMaintenance && !this.config.observationOnly &&
            (!s.lastRestoreAt || this.clock() - s.lastRestoreAt >= this.config.repeatWindowSeconds)) {
          s.lastRestoreAt = this.clock(); this.store.save(); restore = true;
        }
      }
    } finally { this.busy = false; this.drainStop(); }
    if (restore && !this.busy) this.request(this.store.value.desired, 'automatic_restore');
  }
}
