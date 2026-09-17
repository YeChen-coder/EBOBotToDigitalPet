// Export event categories, not free-form household conversations or credential-bearing errors.
const patterns = [
  ['broken_pipe', /Broken[Pp]ipe|Broken pipe/],
  ['connection_refused', /ConnectionRefusedError|Connection refused/],
  ['connection_reset', /ConnectionResetError|Connection reset/],
  ['timeout', /TimeoutError|timed out/],
  ['dns_failure', /gaierror|Name or service not known|Temporary failure in name resolution/],
  ['authentication_failed', /Unauthorized|invalid_api_key|authentication failed/i],
  ['rate_limited', /rate_limit_exceeded|Too Many Requests/],
  ['memory_exhausted', /MemoryError|Out of memory/],
  ['disk_full', /No space left on device/],
  ['media_restart', /Restarting.*(?:ffmpeg|RTSP)|restarting.*(?:ffmpeg|RTSP)/],
];
export function diagnosticEvents(text) {
  const events = [];
  for (const line of text.split(/\r?\n/)) {
    const stamp = /^(\d{4}-\d\d-\d\dT[\d:.]+Z)/.exec(line)?.[1] || null;
    for (const [event, pattern] of patterns) if (pattern.test(line)) events.push({ at: stamp, event });
  }
  return events.slice(-80);
}
