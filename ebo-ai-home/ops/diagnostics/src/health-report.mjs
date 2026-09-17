export const escapeHtml = value => String(value ?? '—').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
export const localTime = at => at ? new Date(typeof at === 'number' ? at * 1000 : at).toLocaleString('zh-CN', { timeZone: 'America/Toronto', hour12: false }) : '未保留';

export function assessHealth(data, at = Date.now() / 1000) {
  const issues = [];
  const s = data.state;
  if (!s?.lastTick || at - s.lastTick > 150) issues.push('Watcher 心跳缺失或超过 150 秒');
  if (data.bridge?.ok !== true) issues.push('宿主机 Bridge 不可达');
  if (data.bridge?.maintenance || data.bridge?.observationOnly) issues.push('宿主机处于维护/观察模式');
  if (data.bridge?.runtimeEnvironment !== s?.runtimeEnvironment) issues.push('监控环境未确认一致');
  if (data.watcher?.ok !== true || data.watcher?.mode !== 'active') issues.push('Watcher 未处于健康的主动监控模式');
  for (const name of ['watcher', 'diagnostic-service', 'codex-triage', 'codex-worker']) {
    const c = data.containers?.find(c => c.service === name);
    if (!c || c.status !== 'running' || c.health !== 'healthy') issues.push(`${name} 容器异常或不可读`);
  }
  for (const name of ['diagnostic-service', 'codex-triage', 'codex-worker']) {
    const p = data.providers?.[name];
    if (p?.health?.ok !== true) issues.push(`${name} 服务不可读`);
    if (name.startsWith('codex-') && p?.health?.credentialConfigured !== true) issues.push(`${name} 缺少模型凭据`);
    if (!Array.isArray(p?.jobs)) issues.push(`${name} 任务记录不可读`);
    const lastRealJob = [...p?.jobs || []].filter(j => !j.id?.startsWith('smoke-') && ['completed', 'failed'].includes(j.status)).sort((a,b) => (b.createdAt || 0) - (a.createdAt || 0))[0];
    if (lastRealJob?.status === 'failed') issues.push(`${name} 最近一次实际诊断失败（${lastRealJob.error || '原因未保留'}），尚无后续成功诊断记录`);
    for (const j of p?.jobs || []) if (['running', 'queued'].includes(j.status) && at - j.createdAt > (j.timeoutSeconds || 600) + 120) issues.push(`${name} 存在超时未结束任务 ${j.id}`);
  }
  for (const x of s?.lastSample?.evidence?.samples || []) {
    const cloud = x.evidence?.cloud;
    if (cloud && (!cloud.observedAt || at - cloud.observedAt > (data.maxAges?.[x.target] || 180))) issues.push(`${x.target} 云端采样过期`);
    if (x.diagnosticEligible === false && x.status === 'fault') issues.push(`${x.target} 监控故障：${x.code}`);
  }
  const business = !s?.lastTick || at - s.lastTick > 150 || issues.some(x => /云端采样过期|监控故障|Bridge 不可达/.test(x)) ? 'unknown' : s.lastSample?.status || 'unknown';
  return { agent: issues.length ? 'attention' : 'healthy', business, issues,
    modelExecution: '未在本次检查调用模型；凭据存在及服务存活不证明当前模型请求一定成功' };
}

export function incidentRows(state, providers, archive = {}) {
  const rows = { ...archive };
  const jobs = providers?.['diagnostic-service']?.jobs || [];
  for (const [target, scope] of Object.entries(state?.scopes || {})) {
    for (const i of [...scope.closed || [], ...scope.incident ? [scope.incident] : []]) {
      const prior = rows[i.id] || {};
      const job = jobs.find(j => j.id === i.id);
      const taskIds = [...new Set((i.observations || []).flatMap(o => o.evidence?.cloud?.tasks?.map(t => t.taskArn.split('/').at(-1)) || []))];
      rows[i.id] = { ...prior, ...i, target, code: i.code || prior.code || job?.symptom || '历史未保留故障原因',
        taskIds: taskIds.length ? taskIds : i.taskIds?.length ? i.taskIds : prior.taskIds || [],
        modelJob: job?.status || prior.modelJob || null,
        tier: job || i.jobSubmitted || prior.jobSubmitted ? '已提交模型诊断（分级见任务表）' : i.action || prior.action || i.outcome === 'recovered_after_action' ? '固定规则恢复' : 'Watcher 检测/复检；未发现模型任务',
        phase: i.outcome ? 'closed' : i.phase, outcome: i.outcome || null };
      // Persist only structured incident metadata, never the observation payload.
      delete rows[i.id].observations; delete rows[i.id].initialEvidence; delete rows[i.id].finalEvidence; delete rows[i.id].job;
    }
  }
  return rows;
}

function renderReportEnglish(data) {
  const e = escapeHtml;
  const time = at => at ? new Date(typeof at === 'number' ? at * 1000 : at).toLocaleString('en-CA', { timeZone: 'America/Toronto', hour12: false }) : 'Not retained';
  const status = value => ({ healthy:'Healthy', attention:'Needs attention', fault:'Fault', unknown:'Unknown', running:'Running', completed:'Completed', failed:'Failed', cancelled:'Cancelled', queued:'Queued', recovered:'Recovered', unresolved:'Unresolved' }[value] || value);
  const issue = value => {
    const exact = { 'Watcher 心跳缺失或超过 150 秒':'Watcher heartbeat is missing or older than 150 seconds.', '宿主机 Bridge 不可达':'The host Bridge is unreachable.',
      '宿主机处于维护/观察模式':'The host is in maintenance or observation-only mode.', '监控环境未确认一致':'The monitored runtime does not match the selected runtime.',
      'Watcher 未处于健康的主动监控模式':'The Watcher is not in healthy active-monitoring mode.' };
    if (exact[value]) return exact[value];
    return value.replace(/ 容器异常或不可读$/, ' container is unhealthy or unreadable.').replace(/ 服务不可读$/, ' service is unreadable.')
      .replace(/ 缺少模型凭据$/, ' is missing model credentials.').replace(/ 任务记录不可读$/, ' job records are unreadable.')
      .replace(/ 云端采样过期$/, ' cloud sample is stale.').replace(/ 监控故障：/, ' monitoring fault: ');
  };
  const table = (headers, rows) => `<div class="scroll"><table><thead><tr>${headers.map(h => `<th>${e(h)}</th>`).join('')}</tr></thead><tbody>${rows.length ? rows.map(r => `<tr>${r.map(c => `<td>${e(c)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${headers.length}">No records</td></tr>`}</tbody></table></div>`;
  const cutoff = Date.parse(data.generatedAt) / 1000 - 86400;
  const incidents = Object.values(data.incidents || {}).sort((a, b) => (b.startedAt || b.endedAt) - (a.startedAt || a.endedAt));
  const jobs = Object.entries(data.providers || {}).flatMap(([provider, p]) => (p.jobs || []).map(j => ({ ...j, provider })));
  const cloudJobs = jobs.filter(j => j.target === 'cloud-ebo' && !j.id.startsWith('smoke-'));
  const h = data.assessment, audit = data.cloudDay;
  const cloudRows = (audit?.targets || []).flatMap(t => t.containers.map(c => [t.target, c.name, c.count, c.unhealthy, c.complete ? 'All pages read' : 'Incomplete', `${Math.round(c.maxGapSeconds)} seconds`, JSON.stringify(c.counters)]));
  const episodes = (audit?.targets || []).flatMap(t => t.containers.flatMap(c => c.episodes.map(x => [c.name, time(x.start), time(x.lastBadAt), x.recoveredAt ? time(x.recoveredAt) : 'Not confirmed in this segment', x.code, x.samples, x.taskId])));
  const stage = j => [j.result?.diagnosis, j.result?.triage?.diagnosis || j.result?.triage, j.result?.advanced?.diagnosis || j.result?.advanced]
    .filter(d => d?.summary).map(d => [d.summary, ...(d.recommendations || []).map(r => `Guidance: ${r}`), ...(d.evidence || []).map(r => `Evidence: ${r}`)].join('\n')).join('\n\n') || j.error || 'No completed report';
  const tier = value => ({'已提交模型诊断（分级见任务表）':'Model diagnosis submitted (see job table for tier)','固定规则恢复':'Rule-based recovery','Watcher 检测/复检；未发现模型任务':'Watcher detection/recheck; no model job found'}[value] || value);
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EBO Diagnostic Agent status</title>
<style>body{font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif;background:#eef2f6;color:#162735;margin:0;padding:32px}main{max-width:1400px;margin:auto}h1{font-size:30px}h2{margin-top:34px}p{color:#4d6070}.cards{display:flex;gap:16px;flex-wrap:wrap}.card{background:white;border-radius:12px;padding:20px;flex:1;min-width:210px;box-shadow:0 2px 10px #152d4010}.value{font-size:25px;font-weight:700}.healthy{color:#087653}.attention,.fault{color:#b44421}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:12px;border-bottom:1px solid #e1e7ed;vertical-align:top;overflow-wrap:anywhere}th{background:#dfe8ef}td{max-width:450px;white-space:pre-line}.scroll{overflow:auto;border-radius:10px}.note{padding:14px;background:#fff6de;border-radius:9px}a{color:#14699e}#stale{font-weight:bold}</style>
<main><p><a href="http://127.0.0.1:8179" target="_top">Back to Runtime & Diagnostics</a></p><h1>Diagnostic Agent evidence</h1><p>Generated ${e(time(data.generatedAt))} (Toronto time) · selected runtime ${e(data.state?.runtimeEnvironment)} · collected every 60 seconds; page refreshes every 30 seconds</p>
<p id="stale"></p><div class="cards"><div class="card">Selected workload<div class="value ${e(h.business)}">${e(status(h.business))}</div>Last functional sample ${e(time(data.state?.lastTick))}</div><div class="card">Diagnostic Agent infrastructure<div class="value ${e(h.agent)}">${h.agent === 'healthy' ? 'Healthy' : 'Needs attention'}</div>Heartbeat, services, credential files, job backlog, and telemetry freshness</div><div class="card">Cloud events in last 24 hours<div class="value">${incidents.filter(i => i.target === 'cloud-ebo' && (i.startedAt >= cutoff || i.endedAt >= cutoff || !i.outcome)).length}</div>Cloud target; includes open events crossing the window</div><div class="card">Cloud model jobs in last 24 hours<div class="value">${cloudJobs.filter(j => j.provider === 'diagnostic-service' && j.createdAt >= cutoff).length}</div>Installation smoke tests excluded</div></div>
${h.issues.length ? `<p class="note">${h.issues.map(x => e(issue(x))).join('<br>')}</p>` : ''}<p class="note">No model was called by this check. Existing credentials and live services do not prove that a current model request will succeed. Historical closure records retain only timestamps and outcomes; old causes, Task identities, and exact handling stages cannot be reconstructed. Samples and observed event metadata are retained from the time this report was enabled.</p>
<h2>Current components</h2>${table(['Component','Process','Docker health','Started','Restart count'], (data.containers || []).map(c => [c.service, status(c.status), status(c.health), time(c.startedAt), c.restartCount]))}
${table(['Service','HTTP','Model / reasoning','Credential file'], Object.entries(data.providers || {}).map(([name, p]) => [name, p.health?.ok ? 'Reachable' : 'Unreachable', [p.health?.model, p.health?.effort].filter(Boolean).join(' / '), p.health?.credentialConfigured === undefined ? 'Not applicable' : p.health?.credentialConfigured ? 'Present (no paid verification)' : 'Missing']))}
<h2>Cloud Task evidence (not applicable in local mode)</h2>${table(['Target','Service','Task ID','Task health','Containers','Functional sample'], (data.state?.lastSample?.evidence?.samples || []).flatMap(s => (s.evidence?.cloud?.tasks || []).map(t => [s.target, s.evidence.cloud.service?.name, t.taskArn?.split('/').at(-1), status(t.health), t.containers?.map(c => `${c.name}: ${status(c.health)}`).join('\n'), s.code])))}
<h2>Watcher incident history and outcomes</h2>${table(['Target / event ID','Start → end','Cause / Task','Handling tier','Outcome'], incidents.map(i => [`${i.target}\n${i.id}`, `${time(i.startedAt)} → ${i.endedAt ? time(i.endedAt) : 'Ongoing'}`, `${i.code}\n${i.taskIds?.join(', ') || 'Task identity not retained'}`, tier(i.tier), status(i.outcome || i.phase)]))}
<h2>Model jobs: triage and advanced stages</h2><p>smoke-* entries are synthetic installation tests. completed means diagnosis execution finished; business recovery still requires Watcher verification. cancelled is not counted as success.</p>${table(['Tier','Job / target','Time','Execution result','Diagnostic summary'], jobs.sort((a,b) => b.createdAt - a.createdAt).map(j => [j.provider, `${j.id}\n${j.target || 'unknown'}${j.id.startsWith('smoke-') ? ' (installation test)' : ''}`, time(j.createdAt), status(j.status), stage(j)]))}
<h2>Previous-day cloud log audit (independent snapshot)</h2><p>${audit ? `${e(time(audit.from))} — ${e(time(audit.to))}; this is a manual audit window and does not rescan AWS when the page refreshes.` : 'No historical scan has run yet.'} Cloud health logs are emitted about every 15 seconds. An unhealthy sample does not automatically equal a sustained incident. The previous local state retained only about 20 samples, so it cannot prove that every historical anomaly was observed locally.</p>${table(['Target','Container','Healthy samples','Unhealthy samples','Pagination','Largest sample gap (including edges)','Recovery/reconnect counter delta'], cloudRows)}
${table(['Container','First unhealthy','Last unhealthy','Later healthy','Cause','Samples','Task'], episodes)}
<h2>Files and evidence</h2><p><a href="latest.json">Current structured status</a> · <a href="incidents.json">Incident archive</a> · <a href="cloud-day.json">Previous-day cloud audit</a> · <a href="README.zh-CN.md">Usage guide</a></p><p>samples-YYYY-MM-DD.jsonl: the reporter writes one row per minute after it is enabled; it makes no claim about earlier full-day local coverage. The reporter depends on this computer being powered on and signed in. The page marks data stale after three minutes. It sends no notifications and triggers no recovery or model request.</p></main>
<script>const generated=${JSON.stringify(data.generatedAt)};function age(){const s=Math.round((Date.now()-Date.parse(generated))/1000);const el=document.getElementById('stale');el.textContent=s>180?'⚠ Report is stale ('+s+' seconds). Current state is unknown; check the reporter and host.':'Report age: '+s+' seconds';el.className=s>180?'attention':'';if(s>180)for(const c of document.querySelectorAll('.card .value')){c.className='value attention';c.textContent='Report stale';}}age();setInterval(age,1000);setTimeout(()=>location.reload(),30000);</script></html>`;
}

export function renderReport(data, language = 'zh') {
  if (language === 'en') return renderReportEnglish(data);
  const e = escapeHtml, time = localTime;
  const table = (headers, rows) => `<div class="scroll"><table><thead><tr>${headers.map(h => `<th>${e(h)}</th>`).join('')}</tr></thead><tbody>${rows.length ? rows.map(r => `<tr>${r.map(c => `<td>${e(c)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${headers.length}">无记录</td></tr>`}</tbody></table></div>`;
  const cutoff = Date.parse(data.generatedAt) / 1000 - 86400;
  const incidents = Object.values(data.incidents || {}).sort((a, b) => (b.startedAt || b.endedAt) - (a.startedAt || a.endedAt));
  const jobs = Object.entries(data.providers || {}).flatMap(([provider, p]) => (p.jobs || []).map(j => ({ ...j, provider })));
  const cloudJobs = jobs.filter(j => j.target === 'cloud-ebo' && !j.id.startsWith('smoke-'));
  const h = data.assessment;
  const audit = data.cloudDay;
  const cloudRows = (audit?.targets || []).flatMap(t => t.containers.map(c => [t.target, c.name, c.count, c.unhealthy, c.complete ? '已读完分页' : '不完整', `${Math.round(c.maxGapSeconds)} 秒`, JSON.stringify(c.counters)]));
  const episodes = (audit?.targets || []).flatMap(t => t.containers.flatMap(c => c.episodes.map(x => [c.name, time(x.start), time(x.lastBadAt), x.recoveredAt ? time(x.recoveredAt) : '本段未确认', x.code, x.samples, x.taskId])));
  const stage = j => [j.result?.diagnosis, j.result?.triage?.diagnosis || j.result?.triage, j.result?.advanced?.diagnosis || j.result?.advanced]
    .filter(d => d?.summary).map(d => [d.summary, ...(d.recommendations || []).map(r => `建议：${r}`), ...(d.evidence || []).map(r => `证据：${r}`)].join('\n')).join('\n\n') || j.error || '无完成报告';
  return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EBO Diagnostic Agent 状态</title>
<style>body{font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif;background:#eef2f6;color:#162735;margin:0;padding:32px}main{max-width:1400px;margin:auto}h1{font-size:30px}h2{margin-top:34px}p{color:#4d6070}.cards{display:flex;gap:16px;flex-wrap:wrap}.card{background:white;border-radius:12px;padding:20px;flex:1;min-width:210px;box-shadow:0 2px 10px #152d4010}.value{font-size:25px;font-weight:700}.healthy{color:#087653}.attention,.fault{color:#b44421}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:12px;border-bottom:1px solid #e1e7ed;vertical-align:top;overflow-wrap:anywhere}th{background:#dfe8ef}td{max-width:450px;white-space:pre-line}.scroll{overflow:auto;border-radius:10px}.note{padding:14px;background:#fff6de;border-radius:9px}a{color:#14699e}#stale{font-weight:bold}</style>
<main><p><a href="http://127.0.0.1:8179" target="_top">返回统一运行与诊断页面</a></p><h1>Diagnostic Agent 详细证据</h1><p>生成于 ${e(time(data.generatedAt))}（多伦多时间） · 当前环境 ${e(data.state?.runtimeEnvironment)} · 每 60 秒采集，页面每 30 秒刷新</p>
<p id="stale"></p><div class="cards"><div class="card">当前所选业务<div class="value ${e(h.business)}">${e(h.business)}</div>最后功能采样 ${e(time(data.state?.lastTick))}</div><div class="card">Diagnostic Agent 基础设施<div class="value ${e(h.agent)}">${h.agent === 'healthy' ? '正常' : '需要检查'}</div>心跳、服务、凭据文件、任务积压与遥测时效</div><div class="card">最近 24 小时云端事件<div class="value">${incidents.filter(i => i.target === 'cloud-ebo' && (i.startedAt >= cutoff || i.endedAt >= cutoff || !i.outcome)).length}</div>云端目标；包含跨窗口未关闭事件</div><div class="card">最近 24 小时云端模型任务<div class="value">${cloudJobs.filter(j => j.provider === 'diagnostic-service' && j.createdAt >= cutoff).length}</div>排除安装 smoke 测试</div></div>
${h.issues.length ? `<p class="note">${h.issues.map(e).join('<br>')}</p>` : ''}<p class="note">${e(h.modelExecution)}。历史故障关闭记录只保留了时间和结果，旧事件的原因、Task 身份和精确处理阶段无法补证。自此报告启用起另存采样和观察到的事件元数据。</p>
<h2>当前组件</h2>${table(['组件', '进程', 'Docker 健康', '启动时间', '重启计数'], (data.containers || []).map(c => [c.service, c.status, c.health, time(c.startedAt), c.restartCount]))}
${table(['服务', 'HTTP', '模型 / 推理', '凭据文件'], Object.entries(data.providers || {}).map(([name, p]) => [name, p.health?.ok ? '可达' : '不可达', [p.health?.model, p.health?.effort].filter(Boolean).join(' / '), p.health?.credentialConfigured === undefined ? '不适用' : p.health.credentialConfigured ? '存在（未做付费验证）' : '缺失']))}
<h2>云端 Task 证据（本地模式不适用）</h2>${table(['目标', '服务', 'Task ID', 'Task 健康', '容器', '功能采样'], (data.state?.lastSample?.evidence?.samples || []).flatMap(s => (s.evidence?.cloud?.tasks || []).map(t => [s.target, s.evidence.cloud.service?.name, t.taskArn?.split('/').at(-1), t.health, t.containers?.map(c => `${c.name}: ${c.health}`).join('\n'), s.code])))}
<h2>Watcher 历史事件及处理结果</h2>${table(['目标 / 事件 ID', '开始 → 结束', '原因 / Task', '处理层级', '结果'], incidents.map(i => [`${i.target}\n${i.id}`, `${time(i.startedAt)} → ${i.endedAt ? time(i.endedAt) : '进行中'}`, `${i.code}\n${i.taskIds?.join(', ') || 'Task 身份未保留'}`, i.tier, i.outcome || i.phase]))}
<h2>模型任务：一线与高级分开列出</h2><p>smoke-* 是合成安装测试；completed 表示诊断执行完成，业务恢复仍以 Watcher 复检为准。cancelled 不计作成功。</p>${table(['层级', '任务 / 目标', '时间', '执行结果', '诊断摘要'], jobs.sort((a,b) => b.createdAt - a.createdAt).map(j => [j.provider, `${j.id}\n${j.target || 'unknown'}${j.id.startsWith('smoke-') ? '（安装测试）' : ''}`, time(j.createdAt), j.status, stage(j)]))}
<h2>过去一天云端日志审计（独立快照）</h2><p>${audit ? `${e(time(audit.from))} — ${e(time(audit.to))}；这是手动审计窗口，不随页面刷新重新扫描 AWS。` : '尚未运行历史扫描。'} 健康日志由云端约每 15 秒产生；异常样本不自动等于一次持续故障。本地原有状态只保留约 20 个采样，无法证明每个历史异常都曾被本地看到。</p>${table(['目标', '容器', '健康样本数', '异常样本数', '分页', '最大采样间隔（含窗口边缘）', '窗口内恢复/重连计数增量'], cloudRows)}
${table(['容器', '首次异常', '最后异常', '后续健康', '原因', '样本数', 'Task'], episodes)}
<h2>文件与证据</h2><p><a href="latest.json">当前结构化状态</a> · <a href="incidents.json">事件归档</a> · <a href="cloud-day.json">云端一天审计</a> · <a href="README.zh-CN.md">使用说明</a></p><p>samples-YYYY-MM-DD.jsonl：报告器从启用时开始每分钟写一行；没有对之前全天本地覆盖率作推断。报告器依赖本机登录和供电，页面超过 3 分钟未更新会显示过期。不会发通知或触发恢复/模型请求。</p></main>
<script>const generated=${JSON.stringify(data.generatedAt)};function age(){const s=Math.round((Date.now()-Date.parse(generated))/1000);const el=document.getElementById('stale');el.textContent=s>180?'⚠ 报告已过期（'+s+' 秒）；当前状态未知，请检查报告器和本机运行情况。':'报告年龄 '+s+' 秒';el.className=s>180?'attention':'';if(s>180)for(const c of document.querySelectorAll('.card .value')){c.className='value attention';c.textContent='报告已过期';}}age();setInterval(age,1000);setTimeout(()=>location.reload(),30000);</script></html>`;
}
