import json
import time
from unittest.mock import Mock, patch
from config import Config
from ebo_transport import AudioStore, Speaker, EboAPI
from state import RuntimeState


def test_stream_failure_uses_the_same_ebo_wav_talk_fallback(tmp_path):
    state=RuntimeState()
    store=AudioStore(tmp_path,state)
    ebo=Mock()
    speaker=Speaker(Config(),ebo,store,state)
    pcm=b'\0\0'*12000
    with patch('ebo_transport.websocket.create_connection',side_effect=OSError('unavailable')):
        speaker.stream_delta(pcm,'output')
        speaker.finish_stream(pcm,'output')
        deadline=time.monotonic()+3
        while not ebo.command.called and time.monotonic()<deadline:
            time.sleep(.01)
    assert (tmp_path/'reply-output.wav').exists()
    assert ebo.command.call_args.args==('talk','http://realtime-assistant:8099/audio/reply-output.wav')
    assert state.snapshot()['speaker_stream_fallbacks']==1


def test_stream_protocol_is_unchanged_and_reports_actual_engine_progress(tmp_path):
    state=RuntimeState()
    speaker=Speaker(Config(),Mock(),AudioStore(tmp_path,state),state)
    stream=speaker._new_stream('output')
    speaker._handle_stream_status(stream,json.dumps({'type':'progress','played_ms':240}))
    assert speaker.output_metrics('output')['played_ms']==240
    assert state.snapshot()['speaker_stream_played_ms']==240


def test_capture_failure_does_not_wake_a_healthy_or_intentionally_disabled_microphone():
    for status in ('receiving','muted','disabled','monitor_stale','monitor_error'):
        state = RuntimeState()
        now = time.time()
        state.update(engine_audio_monitor_enabled=True, engine_audio_checked_at=now,
                     engine_audio_health={'observed_at':now,'status':status,
                                          'source_audio_ok':status=='receiving','last_packet_at':now,'last_pcm_at':now})
        api = EboAPI(Config(),state)
        api.command = Mock()
        api.wake_if_due()
        assert not api.command.called


def test_missing_video_telemetry_does_not_hide_verified_mic_audio():
    now = time.time()
    health = {'observed_at':now,'last_packet_at':now,'last_pcm_at':now,
              'status':'receiving','source_audio_ok':True}
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps([{'node':'ebo','audio_health':health}]).encode()
    with patch('ebo_transport.request.urlopen',return_value=response):
        result = EboAPI(Config(ebo_api_token='test-token'),RuntimeState()).media_health()
    assert result['audio'] == health
    assert result['video']['status'] == 'monitor_error'
    assert not result['video']['source_video_ok']
