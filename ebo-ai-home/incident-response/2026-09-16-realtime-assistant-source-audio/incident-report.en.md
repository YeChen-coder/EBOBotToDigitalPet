# Incident Report: Real-time Assistant Robot Source Audio Outage

## Incident summary

- Date: 2026-09-16
- Status: Fixed and verified live
- Affected path: robot microphone input between local `ebo-engine` and `realtime-assistant`
- Watcher fault code: `container_unhealthy`
- Internal correlation ID: removed from the public report
- User impact: video, the OpenAI Realtime session, and the Assistant process remained online, but robot microphone audio did not reach the Assistant. Local speech therefore could not be heard, transcribed, or answered reliably.
- Data handling: the investigation did not inspect recordings, household transcripts, or credentials.

## Conclusion

This was not normal silence caused by nobody speaking, and the container process had not exited. The robot microphone continuously transported audio before an RTC reconnection. A brief video interruption caused the complete Agora RTC session to be rebuilt; video recovered, but the robot did not resume publishing its microphone track. The old audio recovery timer started when the RTC connection was created, while the robot joined only after the primary retry had already run. The delayed retry after the robot joined only subscribed again and did not resend the command that opens the robot microphone, leaving source health permanently at `no_source_packets`.

The fix starts recovery from the actual robot-joined event and uses bounded backoff to repeat both microphone-open and audio-subscribe operations until real PCM arrives. The worker is constrained to the current RTC generation, current audio observer, connection state, and global microphone privacy setting. It cannot operate on a stale session or open a microphone that the user explicitly disabled.

## Timeline

The public report preserves causal order while omitting household wall-clock times and raw production counters:

| Phase | Event |
|---|---|
| Healthy baseline | The initial RTC session received the robot audio track; source audio became `receiving` and remained stable for an extended period. |
| Trigger | Realtime Assistant detected unavailable RTSP and requested EBO wake plus camera/on. Engine found no flowing video and started a forced RTC rebuild. |
| First reconnect | The replacement RTC/RTM session connected before the robot joined. Engine reported `no_source_packets`; the old watchdog retried too early and PCM remained absent. |
| Second reconnect | Video recovery caused another RTC rebuild. Its watchdog retry again ran before the robot joined. |
| Robot rejoins | Microphone-open and subscribe calls returned successfully, but the old delayed logic retried subscription only. No track callback, network-byte growth, or PCM followed. |
| Partial recovery | Video recovered while source audio stayed at zero, so Docker Health correctly remained `unhealthy`. |
| Remediation | After the full test suite passed, the fixed Engine image was built and only `ebo-engine` was recreated. |
| Validation | Source audio returned to `receiving`; consecutive samples showed monotonically increasing received bytes, stable expected bitrate, and fresh PCM timestamps. Assistant and Docker Health returned to healthy. |
| Closure | Watcher's next sample returned to `healthy`, and the incident closed with `outcome=recovered`. |

## Detection and diagnosis

Docker Desktop's green indicator only shows that the container process is running. The Compose healthcheck reads the Assistant `/health` top-level `ok` value, which requires the Realtime connection, media transport, and real robot source audio to be healthy together. A container can therefore be `running` while Docker Health is `unhealthy`.

The critical fault state was:

```text
realtime_connected=true
video_streaming=true
audio_streaming=true
transport_media_ok=true
source_audio_ok=false
source_audio_status=no_source_packets
received_bytes=0
last_packet_at=null
last_pcm_at=null
ok=false
```

`audio_streaming=true` only means the Assistant FFmpeg audio pipeline still produces output, which can include silence padding. `source_audio_ok` independently proves whether upstream robot packets are arriving. A quiet room still produces encoded audio packets and should not cause hours of `no_source_packets`.

## Root-cause analysis

### Trigger

RTSP video stopped. Assistant media recovery requested wake and camera/on, and Engine rebuilt its Agora RTC session because video was not flowing.

### Direct cause

After the RTC rebuild, the robot did not resume microphone media publication. The SDK subscription state became subscribed, but no audio-track subscription callback, first remote audio frame, increasing network byte count, or PCM callback followed.

### Contributing software defects

1. The audio watchdog started when the RTC connection was created rather than when the robot actually joined.
2. After the second reconnect, the watchdog retried before the robot joined, so the important retry ran too early.
3. `on_user_joined` sent only one microphone-open command.
4. The old 2.5-second delayed retry called `subscribe_audio` only and did not resend `OP_AUDIO_LISTEN`.
5. Once video recovered, the Assistant RTSP recovery path stopped. The source-audio monitor intentionally reported rather than blindly overriding microphone privacy.
6. Docker `restart: unless-stopped` does not restart an unhealthy container, and Watcher treated `container_unhealthy` as non-recoverable.

### Ruled out

- Nobody speaking: quiet audio packets increased continuously before the incident.
- A persistent microphone hardware failure: the same robot sent stable audio at the expected bitrate for an extended period before the event.
- OpenAI Realtime disconnection: the Realtime session stayed connected and rotated normally.
- A sustained video outage: video recovered and continued flowing normally.
- Global privacy mute: `listen=true`; the source state was not `muted`.

## Remediation

Changed files:

- `ha-enabot/ebo/ebo_bridge.py`
- `ha-enabot/ebo/tests/test_audio_health.py`

Implemented changes:

1. Added a bounded retry schedule of `2.5s, 5s, 10s, 20s, 30s`.
2. Recovery now starts from `on_user_joined`, not RTC connection creation.
3. Every attempt performs both:
   - `OP_AUDIO_LISTEN {type: 1, open: 1}` again;
   - `subscribe_audio` and `subscribe_all_audio` again.
4. Retries stop immediately after real PCM arrives.
5. A replaced RTC or observer invalidates the old recovery worker, preventing cross-session actions.
6. Shutdown, disabled audio, or an explicit global microphone mute stops recovery without overriding privacy.
7. The sequence is bounded, preventing endless command or reconnect loops.
8. Health semantics remain strict; the fix did not hide the incident by weakening the `ok` contract.

## Testing and validation

### Automated tests

- Focused audio-health and functional tests: 47 passed.
- Complete EBO Engine suite: 117 passed, 1 skipped as designed.
- Test environment: Python 3.11 container matching the production image.
- New coverage verifies:
  - repeated microphone-open and subscribe operations after robot join;
  - stopping after PCM arrives;
  - no recovery after an explicit privacy mute;
  - no action from stale RTC/observer workers.

### Build and live validation

- Built `ebo-ai-home/ebo-engine:0.26.100` successfully.
- Recreated only `ebo-engine`; Home Assistant was not restarted.
- Four consecutive live samples showed `receiving`, monotonically increasing network bytes, stable expected bitrate, fresh PCM timestamps, `Assistant ok=true`, and healthy Docker status.

These independent signals prove that real source audio recovered rather than silence padding creating a false positive. Exact wall-clock times and raw counters are omitted from the public report.

## Follow-up recommendations

1. Expose audio-recovery attempt counters and last-success time in the health endpoint so future reports can display recovery directly.
2. Add a higher-level delayed-robot-join integration scenario; this change already adds deterministic logic-level regression tests.
3. Keep the strict source-audio health contract. Container Running, healthy video, or FFmpeg output alone must not be treated as healthy voice input.

## Rollback

If the new recovery logic causes unexpected behavior, revert this code commit, rebuild `ebo-engine`, and recreate only that container. Rollback does not change Home Assistant configuration, household recordings, transcripts, or robot privacy settings.
