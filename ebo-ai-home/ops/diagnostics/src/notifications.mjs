import { jsonFetch, audit } from './common.mjs';

export function notificationText(incident, kind) {
  // Do not forward model output or raw logs to Telegram; keep those in the local incident report.
  return `[EBO ${kind}] incident=${incident.id}\ntarget=${incident.target || 'infrastructure'}\n` +
    `symptom=${incident.code || 'unknown'}\nphase=${incident.phase || kind}\n` +
    `action=${incident.action?.status || 'none'}\n` +
    (kind === 'recovered' ? '功能复检已恢复。' : incident.phase === 'monitoring_failed' ?
      '监控数据持续不可用，无法确认业务健康。请检查采集凭据、网络与日志时效。' : '服务持续异常，需要查看本地诊断记录。');
}
export async function notify(incident, kind, bridge) {
  const message = notificationText(incident, kind);
  const channels = [];
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (token && chatId) channels.push(jsonFetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST', body: { chat_id: chatId, text: message }, timeout: 8000,
  }).then(r => { if (r.ok !== true) throw new Error('telegram_rejected'); }));
  if (bridge) channels.push(bridge.notify({ id: `${incident.id}-${kind}`, message }));
  if (!channels.length) throw new Error('no_notification_channel');
  const results = await Promise.allSettled(channels);
  if (!results.some(r => r.status === 'fulfilled')) throw new Error('notification_failed');
  audit('notification_delivered', { incident: incident.id, kind });
}
