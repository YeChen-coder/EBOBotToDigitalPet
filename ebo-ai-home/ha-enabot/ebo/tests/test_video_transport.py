"""Transport recovery must not block RTC callbacks or manufacture live source health."""
import json
import os
import subprocess
import sys
import threading
import time
import types
from unittest.mock import Mock, patch

import pytest

observer = types.ModuleType('agora.rtc.video_frame_observer')
observer.IVideoFrameObserver = type('IVideoFrameObserver', (), {})
sys.modules.setdefault(observer.__name__, observer)
from ebo_video import VideoPipeline


@pytest.fixture
def pipeline():
    with patch.object(VideoPipeline, '_start_mediamtx'):
        video = VideoPipeline(fps=20)
    yield video
    video.stop()


def frame(value=1):
    return types.SimpleNamespace(width=4, height=4, y_buffer=bytes([value])*16,
                                 u_buffer=b'\x80'*4, v_buffer=b'\x80'*4,
                                 y_stride=4, u_stride=2, v_stride=2)


def test_callback_keeps_newest_frame_without_spawning_encoder(pipeline):
    pipeline.feeding = True
    with patch.object(pipeline, '_start_ffmpeg') as start:
        pipeline.on_frame('', 1, frame(1))
        pipeline.on_frame('', 1, frame(2))
        assert not start.called
    assert pipeline._pending[0] == bytes([2])*16
    assert pipeline.frames == 2


def test_repeated_output_cannot_make_old_robot_frames_healthy(pipeline):
    pipeline.feeding = True
    pipeline.on_frame('', 1, frame())
    assert pipeline.health_snapshot()['source_video_ok']
    with patch('ebo_video.time.time', return_value=pipeline._last_frame+25):
        pipeline._last_output = time.time()
        health = pipeline.health_snapshot()
        assert not health['source_video_ok']
        assert health['status'] == 'source_stale'
    assert not pipeline.health_snapshot(connected=False)['source_video_ok']
    assert not pipeline.health_snapshot(enabled=False)['source_video_ok']


def test_audio_queue_drops_old_backlog_and_keeps_latest_pcm(pipeline):
    pipeline.feeding = True
    pipeline.write_audio(b'\x01\x00'*1600)
    pipeline.write_audio(b'\x02\x00'*400)
    assert len(pipeline._audio_pending) == 3200  # exactly 200ms @ 8kHz
    assert pipeline._audio_pending[-800:] == b'\x02\x00'*400


def test_stop_kills_and_reaps_before_closing_pipe(pipeline):
    events = []
    ff = Mock()
    ff.kill.side_effect = lambda: events.append('kill')
    ff.wait.side_effect = lambda **kwargs: events.append('wait')
    ff.stdin.close.side_effect = lambda: events.append('close')
    pipeline.ff = ff
    pipeline._stop_ffmpeg()
    assert events == ['kill','wait','close']
    assert pipeline.ff is None


def test_mute_clears_frame_and_audio_backlog(pipeline):
    pipeline.feeding = True
    pipeline.on_frame('', 1, frame())
    pipeline.write_audio(b'\x01\x00'*800)
    pipeline.stop_feed()
    assert pipeline.health_snapshot()['status'] == 'camera_off'
    assert not pipeline._pending and not pipeline._audio_pending
    assert not pipeline._last_frame


@pytest.mark.parametrize('result', [0, -1001])
def test_source_recovery_retries_keyframes_without_rejoining_or_wake_flood(B_mod, monkeypatch, result):
    bridge = B_mod.Bridge.__new__(B_mod.Bridge)
    bridge.video = Mock(feeding=True)
    bridge.video.is_streaming.side_effect = [False]*12+[True]+[False]*2
    bridge.rtc = Mock()
    bridge.rtc.send_intra_request.return_value = result
    bridge.robot_uid = '123'
    bridge.connected = True
    bridge._wake = Mock()
    bridge._force_rejoin = Mock()
    clock = [0]
    waits = []
    logs = []
    class Stop:
        def is_set(self):
            return clock[0] >= 30
        def wait(self, seconds):
            waits.append(seconds)
            clock[0] += seconds
    bridge.stop = Stop()
    monkeypatch.setattr(B_mod.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(B_mod, 'log', lambda *args: logs.append(' '.join(map(str,args))))
    bridge._video_diag()
    assert bridge.rtc.send_intra_request.call_count == 14
    bridge.rtc.send_intra_request.assert_called_with('123')
    assert waits == [2]*15
    assert bridge._wake.call_count == 1
    assert not bridge._force_rejoin.called
    assert sum('decoded video is stale' in msg for msg in logs) == 1
    assert any('fresh decoded frames resumed' in msg for msg in logs)
    assert sum('keyframe request failed' in msg for msg in logs) == (2 if result else 0)


def test_source_recovery_respects_camera_off(B_mod):
    bridge = B_mod.Bridge.__new__(B_mod.Bridge)
    bridge.video = Mock(feeding=False)
    bridge.stop = Mock()
    bridge.stop.is_set.return_value = False
    bridge.rtc = Mock()
    bridge._wake = Mock()
    bridge._video_diag()
    assert not bridge.rtc.send_intra_request.called
    assert not bridge._wake.called


@pytest.mark.skipif(sys.platform != 'linux', reason='Production FFmpeg pipes / MediaMTX run on Linux')
def test_real_rtsp_remains_clocked_during_25_second_video_gap(monkeypatch):
    monkeypatch.setenv('EBO_AUDIO', '1')
    messages = []
    monkeypatch.setattr('ebo_video.log', lambda *args, **kwargs: messages.append(' '.join(map(str,args))))
    # Other bridge tests create default-port pipeline objects while exercising
    # command routing. Keep the real transport integration on its own ports.
    video = VideoPipeline(rtsp_port=8564, path='video-regression', fps=10)
    source = types.SimpleNamespace(width=64, height=64, y_buffer=b'\x40'*4096,
        u_buffer=b'\x80'*1024, v_buffer=b'\x80'*1024, y_stride=64, u_stride=32, v_stride=32)
    reader = None
    try:
        video.start_feed()
        video.on_frame('', 1, source)
        deadline = time.monotonic()+8
        while video._last_output == 0 and time.monotonic() < deadline:
            time.sleep(.05)
        assert video._last_output > 0
        time.sleep(.5)  # allow FFmpeg's RTSP ANNOUNCE / RECORD handshake
        reader = subprocess.Popen(['ffprobe','-v','error','-rtsp_transport','tcp',
            '-timeout','5000000','-i',video.rtsp_url,
            '-show_packets','-show_entries','packet=stream_index,pts_time','-of','compact'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        packets = []
        def receive():
            for line in reader.stdout:
                values = dict(part.split('=',1) for part in line.decode().strip().split('|') if '=' in part)
                if values.get('pts_time') not in (None,'N/A'):
                    packets.append(values)
        receiver = threading.Thread(target=receive,daemon=True)
        receiver.start()
        time.sleep(27)
        assert reader.poll() is None, (reader.stderr.read().decode(), video.health_snapshot(),
                                       video._enc_count, messages[-25:])
        reader.terminate()
        reader.wait(timeout=3)
        receiver.join(timeout=3)
        for index in (0, 1):
            stamps = [float(p['pts_time']) for p in packets if int(p['stream_index'])==index]
            assert len(stamps) > 150  # both video and mic transport keep advancing
            assert stamps[-1]-stamps[0] >= 24
            assert all(-.25 <= b-a < .5 for a, b in zip(stamps,stamps[1:])), stamps[-20:]
        assert video.encoder_restarts == 1
        assert video.health_snapshot()['status'] == 'source_stale'
        video.on_frame('', 1, source)
        assert video.health_snapshot()['source_video_ok']
        # A killed encoder recovers from the retained image, even before another
        # RTC frame arrives. Likewise, a dead MediaMTX must be recreated.
        for kind in ('ff','mediamtx'):
            generation = video.encoder_restarts
            getattr(video,kind).kill()
            getattr(video,kind).wait(timeout=3)
            previous = video._last_output
            deadline = time.monotonic()+10
            while (video._last_output <= previous or video.encoder_restarts <= generation) and time.monotonic()<deadline:
                time.sleep(.05)
            assert video._last_output > previous
            assert video.encoder_restarts > generation
        assert video.encoder_restarts >= 3
        assert video.server_restarts == 2
    finally:
        if reader and reader.poll() is None:
            reader.kill()
            reader.communicate(timeout=3)
        video.stop()
