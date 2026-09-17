import { jsonFetch } from '../src/common.mjs';
const state = await jsonFetch('http://127.0.0.1:8178/state', { token: process.env.DIAGNOSTIC_TOKEN });
if (process.argv.includes('--compact')) {
  console.log(`业务环境：${state.runtimeEnvironment || 'unknown'}；监控：${state.activeTargets?.join(', ') || 'pending'}；排除：${state.excludedTargets?.join(', ') || 'none'}`);
  console.log(`最近检查：${new Date(state.lastTick * 1000).toLocaleString()}`);
  for (const s of state.lastSample?.evidence?.samples || []) console.log(`${s.target}: ${s.status} (${s.code})`);
  const incidents = state.incidents || (state.incident ? [state.incident] : []);
  if (!incidents.length) console.log('当前没有未关闭的故障。');
  for (const i of incidents) console.log(`故障 ${i.id}: ${i.target} / ${i.phase} / ${i.code}`);
  process.exit(0);
}
console.log(JSON.stringify({ runtimeEnvironment: state.runtimeEnvironment, activeTargets: state.activeTargets, excludedTargets: state.excludedTargets, lastTick: state.lastTick, sample: state.lastSample, incident: state.incident && {
  id: state.incident.id, phase: state.incident.phase, code: state.incident.code, notified: state.incident.notified,
  action: state.incident.action, job: state.incident.job,
}, incidents: state.incidents?.map(i => ({ id: i.id, target: i.target, phase: i.phase, code: i.code, notified: i.notified })),
recoveries: state.recoveries, closed: state.scopes ? Object.entries(state.scopes).flatMap(([target, s]) => (s.closed || []).slice(-3).map(x => ({ target, ...x }))) : state.closed?.slice(-5) }, null, 2));
