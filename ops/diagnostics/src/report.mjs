import { jsonFetch, validId } from './common.mjs';
const base = 'http://127.0.0.1:8081';
const options = { token: process.env.DIAGNOSTIC_TOKEN };
const id = process.argv[2];
if (id && !validId(id)) throw new Error('Invalid report id');
if (!id) {
  const { jobs } = await jsonFetch(`${base}/jobs`, options);
  if (!jobs.length) console.log('暂无诊断报告。健康或已通过固定流程恢复时不会调用模型。');
  else for (const j of jobs) console.log(`${j.id}  ${j.status}  ${new Date(j.createdAt * 1000).toLocaleString()}`);
} else {
  const job = await jsonFetch(`${base}/jobs/${id}`, options);
  console.log(`诊断 ${job.id}：${job.status}`);
  if (job.error) console.log(`错误：${job.error}`);
  for (const [label, value] of [['一线', job.result?.triage], ['高级', job.result?.advanced]]) {
    if (!value) continue;
    console.log(`\n${label}：${value.model || value.provider || 'API'} ${value.reasoningEffort || ''}`);
    if (value.skipped || value.failed) { console.log(value.reason || 'failed'); continue; }
    const d = value.diagnosis || value;
    console.log(d.summary || '');
    for (const e of d.evidence || []) console.log(`证据：${e}`);
    for (const r of d.recommendations || []) console.log(`建议：${r}`);
  }
  console.log('\n模型报告不代表故障已恢复；以 Watcher 功能复检为准。');
}
