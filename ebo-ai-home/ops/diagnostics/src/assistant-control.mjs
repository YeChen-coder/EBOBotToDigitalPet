import fs from 'node:fs';
import { parseEnv } from 'node:util';

// Only the local host holds this credential. It is never included in dashboard payloads.
export function createAssistantControl({ runtime, envFile, fetchImpl = fetch }) {
  const call = async (pathname, body) => {
    if (runtime.busy || runtime.status().desired !== 'local') return { code:409, body:{error:'local_runtime_required'} };
    const headers = {};
    if (body) {
      const env = parseEnv(fs.readFileSync(envFile, 'utf8').replace(/^\uFEFF/, ''));
      const token = env.EBO_ASSISTANT_CONTROL_TOKEN || env.EBO_API_TOKEN;
      if (!token) return { code:503, body:{error:'assistant_control_unconfigured'} };
      headers['X-EBO-Control-Token'] = token;
      headers['Content-Type'] = 'application/json';
    }
    try {
      const response = await fetchImpl('http://127.0.0.1:8099' + pathname, {
        method:body ? 'POST' : 'GET', headers, redirect:'error',
        body:body ? JSON.stringify(body) : undefined, signal:AbortSignal.timeout(5000),
      });
      const data = await response.json();
      return { code:response.status, body:data };
    } catch { return { code:503, body:{error:'assistant_unreachable'} }; }
  };
  return { status:() => call('/health'), command:(action, body) => {
    if (!['start','close','pause','resume'].includes(action)) return {code:400,body:{error:'invalid_session_action'}};
    return call((['pause','resume'].includes(action) ? '/assistant/' : '/session/')+action,
      action === 'start' ? {user_id:body.user_id} : {});
  } };
}
