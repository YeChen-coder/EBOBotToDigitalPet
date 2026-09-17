import http from 'node:http';
let broken = process.env.PERSISTENT_FAILURE === 'true';
http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/break') broken = true;
  res.writeHead(200, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ ok: !broken, realtime_connected: true, video_streaming: !broken,
    audio_streaming: true, source_audio_ok: true, source_audio_status: 'receiving', uptime_seconds: 999 }));
}).listen(8188, '0.0.0.0');
