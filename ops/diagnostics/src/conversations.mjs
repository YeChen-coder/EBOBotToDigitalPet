import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';

export const conversationFilter = '{ ($.event = "conversation.user.transcript" || $.event = "conversation.assistant.output") && $.transcript != "" }';
const hash = value => createHash('sha256').update(value).digest('hex');
const DAY = 86400000;
const defaults = { localSeconds: 30, cloudSeconds: 300, idleCloudSeconds: 1800, bootstrapDays: 7,
  retentionDays: 30, overlapSeconds: 600, maxPagesPerPoll: 2, dailyRequestLimit: 600, maxMessages: 20000 };

export function normalizeConversation(row, { role, scope, eventId, eventTime } = {}) {
  if (!role) role = row.event === 'conversation.user.transcript' ? 'user' : row.event === 'conversation.assistant.output' ? 'assistant' : null;
  if (!role || typeof row.transcript !== 'string') return null;
  const at = Number.isFinite(row.received_at) ? row.received_at * 1000 : Date.parse(row.timestamp) || eventTime;
  if (!Number.isFinite(at) || at <= 0) return null;
  const chunked = Number.isInteger(row.chunk_count) && row.chunk_count > 1 && row.chunk_count <= 1024 && Number.isInteger(row.chunk_index) && row.chunk_index >= 0 && row.chunk_index < row.chunk_count;
  if (!chunked && !row.transcript.trim()) return null;
  const message = chunked ? row.transcript : row.transcript.trim();
  const session = String(row.session_started_at || 'unknown');
  const item = role === 'user' ? row.item_id : row.response_id || row.output_id || row.item_id;
  // IDs deduplicate repeated CloudWatch pages and file rewrites, never repeated spoken words.
  const key = item ? `${role}:${session}:${item}` : `${scope}:${role}:${row.event_id || eventId || hash(at + ':' + message)}`;
  return { id: hash(key), at, message, role, scope, session,
    ...(chunked ? { chunk: { key:hash(`${scope}:${row.event_id || key + ':' + at}`),index:row.chunk_index,count:row.chunk_count } } : {}) };
}

export function groupConversations(messages) {
  const groups = []; const last = new Map();
  for (const m of [...messages].sort((a,b) => a.at-b.at || (a.role === b.role ? a.id.localeCompare(b.id) : a.role === 'user' ? -1 : 1))) {
    const scope = m.scope + ':' + m.session; let group = last.get(scope);
    // Legacy logs have no response-to-input ID. Group nearby messages, not inferred causality.
    if (m.role === 'user' || !group || m.at - group.messages.at(-1).at > 120000 || group.messages[0].role !== 'user') {
      group = { id: m.id, at: m.at, messages: [] }; groups.push(group); last.set(scope, group);
    }
    group.messages.push(m); group.at = Math.max(group.at, m.at);
  }
  return groups.sort((a,b) => b.at-a.at || a.id.localeCompare(b.id));
}

// Only reads the two approved text files; WAVs and reply directories are never read.
export async function readLocalConversations(directory, fingerprints = {}) {
  const result = { messages: [], fingerprints: { ...fingerprints }, missing: [], invalid: 0, limited: false };
  for (const [filename,role] of [['transcripts.jsonl','user'],['assistant_outputs.jsonl','assistant']]) {
    let handle;
    try {
      const file = path.join(directory, filename); const stat = await fs.stat(file);
      const version = `${stat.size}:${stat.mtimeMs}`;
      if (fingerprints[filename] === version) continue;
      // Bounded tail: avoids unbounded memory on years of append-only history.
      const bytes = Math.min(stat.size, 8 * 1024 * 1024); const start = stat.size - bytes;
      handle = await fs.open(file, 'r'); const buffer = Buffer.alloc(bytes);
      const read = await handle.read(buffer, 0, bytes, start); let text = buffer.subarray(0, read.bytesRead).toString('utf8');
      if (start > 0) { text = text.slice(text.indexOf('\n') + 1); result.limited = true; }
      const complete = text.endsWith('\n'); const lines = text.split(/\r?\n/);
      // Do not consume half-written JSONL records. Retry even if timestamp resolution is coarse.
      if (!complete) lines.pop(); else result.fingerprints[filename] = version;
      for (const line of lines) {
        if (!line.trim()) continue;
        try { const m = normalizeConversation(JSON.parse(line.replace(/^\uFEFF/, '')), { role, scope: 'local' }); if (m) result.messages.push(m); }
        catch { result.invalid++; }
      }
    } catch (e) { if (e.code === 'ENOENT') result.missing.push(filename); else throw new Error('local_transcripts_unreadable'); }
    finally { await handle?.close(); }
  }
  return result;
}

export class ConversationLog {
  constructor({ store, targets, calls, directory, settings = {}, clock = Date.now, readLocal = readLocalConversations }) {
    Object.assign(this, { store, calls, directory, clock, readLocal });
    this.settings = { ...defaults, ...settings };
    for (const [key,value] of Object.entries(this.settings)) if (!Number.isFinite(value) || value <= 0) throw new Error('invalid_conversation_settings:' + key);
    this.sources = targets.flatMap(t => (t.aws?.containers || []).filter(c => c.name === 'realtime-assistant').map(c => ({
      id: t.id, group: c.logGroup, prefix: c.streamPrefix + '/', target: t,
    })));
    const s = store.value; s.messages ??= []; s.cloud ??= {}; s.local ??= {}; s.budget ??= {}; s.fragments ??= {};
    this.inflight = null; this.version = 0; this.groups = null;
  }
  merge(rows) {
    const s = this.store.value; const records = new Map(s.messages.map(m => [m.id,m])); let changed = false;
    for (let row of rows) {
      if (row.chunk) {
        const { chunk, ...message } = row;
        const pending = s.fragments[chunk.key] ??= { message, count:chunk.count, parts:[] };
        if (pending.count !== chunk.count) continue;
        pending.parts[chunk.index] = row.message;
        if (pending.parts.filter(x => typeof x === 'string').length !== chunk.count) continue;
        row = { ...pending.message, message:pending.parts.join('').trim() }; delete s.fragments[chunk.key];
      }
      if (row.at <= this.clock() + 300000 && JSON.stringify(records.get(row.id)) !== JSON.stringify(row)) { records.set(row.id,row); changed = true; }
    }
    const cutoff = this.clock() - this.settings.retentionDays * DAY;
    for (const [id,f] of Object.entries(s.fragments)) if (f.message.at < cutoff) delete s.fragments[id];
    const sorted = [...records.values()].filter(m => m.at >= cutoff).sort((a,b) => a.at-b.at || a.id.localeCompare(b.id));
    if (sorted.length > this.settings.maxMessages) s.cacheLimited = true;
    s.messages = sorted.slice(-this.settings.maxMessages);
    if (changed || s.messages.length !== records.size) { this.version++; this.groups = null; }
  }
  poll(mode) {
    if (this.inflight) return this.inflight;
    this.inflight = this.collect(mode).finally(() => { this.inflight = null; });
    return this.inflight;
  }
  async collect(mode) {
    const s = this.store.value; const at = this.clock(); const c = this.settings;
    if (!s.local.nextAt || at >= s.local.nextAt) {
      s.local.nextAt = at + c.localSeconds * 1000;
      try {
        const read = await this.readLocal(this.directory,s.local.fingerprints);
        this.merge(read.messages); Object.assign(s.local, { checkedAt: this.clock(), fingerprints: read.fingerprints, missing: read.missing,
          limited: read.limited || s.local.limited, invalid: read.invalid, error: null });
      } catch { s.local.error = 'local_transcripts_unreadable'; }
      this.store.save();
    }
    const day = new Date(at).toISOString().slice(0,10);
    if (s.budget.day !== day) s.budget = { day, requests: 0 };
    for (const source of this.sources) {
      const state = s.cloud[source.id] ??= {};
      const interval = (mode === 'aws' ? c.cloudSeconds : c.idleCloudSeconds) * 1000;
      // Mode changes to cloud can shorten idle delay, but never bypass failure backoff.
      const due = state.error ? state.nextAt : Math.min(state.nextAt || 0, (state.attemptAt || 0) + interval);
      if (at < due) continue;
      state.attemptAt = at; state.nextAt = at + interval; this.store.save();
      try {
        if (state.schema !== 2) {
          state.schema = 2; state.window = null;
          state.historyFrom = at - c.bootstrapDays * DAY;
          state.historyBefore = at - Math.min(c.bootstrapDays,1) * DAY;
        }
        let liveComplete = false;
        for (let page = 0; page < c.maxPagesPerPoll; page++) {
          if (s.budget.requests >= c.dailyRequestLimit) { state.error = 'daily_request_limit'; state.nextAt = Date.parse(day) + DAY; this.store.save(); break; }
          state.historyFrom = Math.max(state.historyFrom, at - c.retentionDays * DAY);
          if (liveComplete && state.historyBefore <= state.historyFrom) break;
          const minStart = at - c.retentionDays * DAY;
          const key = liveComplete ? 'historyWindow' : 'window';
          if (state[key]?.startedAt < at - 23 * 3600000) { state[key].token = null; state[key].startedAt = at; } // Tokens expire; replay deduplicates safely.
          const window = state[key] ??= liveComplete ? { start:Math.max(minStart,state.historyFrom,state.historyBefore-DAY),end:state.historyBefore,startedAt:at } :
            { start: Math.max(minStart, state.through ? state.through - c.overlapSeconds * 1000 : state.historyBefore), end: at, startedAt: at };
          const args = ['logs','filter-log-events','--log-group-name',source.group,'--log-stream-name-prefix',source.prefix,
            '--filter-pattern',conversationFilter,'--start-time',String(Math.floor(window.start)),'--end-time',String(Math.floor(window.end)),
            '--limit','200','--no-paginate'];
          if (window.token) args.push('--next-token',window.token);
          s.budget.requests++; this.store.save(); // Reserve budget before even a failed network call; restarts cannot bypass it.
          const response = await this.calls.get(source.id)(args);
          const rows = [];
          for (const event of response.events || []) {
            try { const m = normalizeConversation(JSON.parse(event.message), { scope: `cloud:${source.id}:${event.logStreamName || ''}`,eventId:event.eventId,eventTime:event.timestamp }); if (m) rows.push(m); }
            catch { state.invalid = (state.invalid || 0) + 1; }
          }
          this.merge(rows); state.checkedAt = this.clock(); state.error = null; state.failures = 0;
          if (!response.nextToken) {
            if (liveComplete) state.historyBefore = window.start; else { state.through = window.end; liveComplete = true; }
            state[key] = null; this.store.save(); continue;
          }
          // Empty pages with a token still require another page; never advance the watermark early.
          if (response.nextToken === window.token) { state.error = 'cloud_pagination_stalled'; this.store.save(); break; }
          window.token = response.nextToken; this.store.save();
        }
      } catch (e) {
        const allowed = ['aws_throttled','aws_access_denied','aws_credentials_unavailable'];
        state.error = allowed.includes(e.message) ? e.message : 'cloud_transcripts_unavailable';
        state.failures = (state.failures || 0) + 1;
        state.nextAt = this.clock() + Math.min(3600000, interval * 2 ** Math.min(state.failures,4)); this.store.save();
      }
    }
  }
  view(limit = 50) {
    const s = this.store.value; const c = this.settings;
    this.groups ??= groupConversations(s.messages);
    const count = Math.min(500,Math.max(1,Number.isInteger(limit) ? limit : 50));
    // Raw event IDs, paths, Task IDs, audio and operational metadata never enter message payloads.
    return { revision: this.version, groups: this.groups.slice(0,count).map(g => ({ id:g.id, messages:g.messages.map(m => ({ timestamp:new Date(m.at).toISOString(),role:m.role,message:m.message })) })),
      hasMore: this.groups.length > count, localCheckedAt:s.local.checkedAt || null,
      cloudCheckedAt:this.sources.length ? Math.min(...this.sources.map(x => s.cloud[x.id]?.checkedAt || 0)) || null : null,
      cloudCatchingUp:this.sources.some(x => {const v=s.cloud[x.id];return !!v?.window || !!v?.historyWindow || v?.historyBefore>v?.historyFrom;}), localError:s.local.error || null,
      cloudError:this.sources.map(x => s.cloud[x.id]?.error).find(Boolean) || null,
      localMissing:!!s.local.missing?.length, limited:!!(s.cacheLimited || s.local.limited),
      invalid:!!(s.local.invalid || Object.values(s.cloud).some(x => x.invalid)),
      partialMessages:Object.keys(s.fragments).length,
      coverage: { bootstrapDays:c.bootstrapDays,retentionDays:c.retentionDays },
      requestsToday:s.budget.requests || 0, dailyRequestLimit:c.dailyRequestLimit };
  }
}
