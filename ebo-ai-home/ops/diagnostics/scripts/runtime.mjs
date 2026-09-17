import { jsonFetch } from '../src/common.mjs';
const mode = process.argv[2];
if (!['aws', 'local', 'stopped'].includes(mode)) throw new Error('Choose aws, local or stopped');
const options = { token: process.env.BRIDGE_TOKEN };
try {
  await jsonFetch('http://127.0.0.1:8177/runtime', { ...options, method: 'POST', body: { mode } });
  console.log('运行选择已保存。实时进度：http://127.0.0.1:8179');
  let prior = '';
  const deadline = Date.now() + 20 * 60 * 1000;
  while (Date.now() < deadline) {
    const state = await jsonFetch('http://127.0.0.1:8177/runtime', options);
    if (state.step !== prior) { console.log(state.step); prior = state.step; }
    if (!state.busy && state.phase !== 'switching') {
      if (state.phase !== 'ready') { console.error(state.message || '状态未确认'); process.exitCode = 1; }
      break;
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  if (Date.now() >= deadline) { console.error('等待超时。请查看 Dashboard，不能据此认为任务已经停止。'); process.exitCode = 1; }
} catch (e) {
  console.error(e.message === 'http_409' ? '另一个状态检查、切换或恢复正在进行，请稍后重试。实时进度：http://127.0.0.1:8179' : '控制请求失败。请启动或更新 Diagnostic Agent，并在 Dashboard 查看当前状态。');
  process.exitCode = 1;
}
