import asyncio
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from runtime import MediaCapture, Supervisor
from standby_voice import VoiceTurn
from test_framework import config, conversation, ready_state


def session():
    return SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()))


def messages(s):
    return [call.args[0].message for call in s.model.send_event.call_args_list]


def test_manual_start_needs_audio_but_not_video_frigate_or_mqtt(config):
    state = ready_state()
    state.update(last_frame_at=0, frigate_ready=False, mqtt_connected=False)
    supervisor = Supervisor(config, state, Mock(), Mock(), Mock())
    with patch('runtime.threading.Thread'):
        assert supervisor.start('father')
    assert supervisor.active.frame_source is supervisor.frame_source
    supervisor.active = None
    with pytest.raises(ValueError, match='media_not_ready'):
        supervisor.start('father', 'face')
    state.update(last_audio_at=time.time()-30)
    with pytest.raises(ValueError, match='media_not_ready'):
        supervisor.start('father')


@pytest.mark.parametrize('failure', [OSError('HTTP failed'), ValueError('bad JPEG'), RuntimeError('unexpected decode failure')])
def test_image_fetch_failure_allows_opening_and_voice_replies(config, tmp_path, failure):
    async def run():
        c = conversation(config, tmp_path, Mock(latest_jpeg=Mock(side_effect=failure)))
        c.ready.set()
        c.initial_turn = VoiceTurn('wake', b'pcm', time.monotonic(), 0, '请讲故事')
        s = session()
        await c.opening(s)
        await asyncio.sleep(.02)
        assert any(m['type'] == 'response.create' for m in messages(s))
        assert not c.stop.is_set() and not c.failed
        assert c.state.snapshot()['visual_last_error'] == type(failure).__name__
    asyncio.run(run())


def test_slow_fetch_has_deadline_and_cannot_queue_workers_or_use_late_picture(config, tmp_path):
    async def run():
        release = threading.Event()
        def fetch():
            release.wait(2)
            return b'late'
        source = Mock(latest_jpeg=Mock(side_effect=fetch))
        c = conversation(config, tmp_path, source)
        c.visual_timeout = .02
        s = session()
        try:
            await asyncio.wait_for(c.refresh_visual_context(s), .2)
            assert c.state.snapshot()['visual_last_error'] == 'TimeoutError'
            await c.refresh_visual_context(s)
            assert source.latest_jpeg.call_count == 1
            await c.on_server_event(s, {'type': 'conversation.item.input_audio_transcription.completed',
                                      'item_id': 'question', 'transcript': '讲个故事'})
            await asyncio.sleep(.06)
            assert any(m['type'] == 'response.create' for m in messages(s))
            assert not any(m['type'] == 'conversation.item.create' for m in messages(s))
            assert not c.failed
        finally:
            release.set()
            await c.visual_fetch_task
    asyncio.run(run())


def test_images_return_after_failure_using_original_ack_and_replacement(config, tmp_path):
    async def run():
        c = conversation(config, tmp_path, Mock(latest_jpeg=Mock(side_effect=[OSError(), b'new', b'newer'])))
        c.latest_image_id = 'stale'
        s = session()
        await c.refresh_visual_context(s)
        assert c.latest_image_id is None
        await c.refresh_visual_context(s)
        first = c.pending_image_id
        await c.on_server_event(s, {'type': 'conversation.item.added', 'item': {'id': first}})
        await c.refresh_visual_context(s)
        second = c.pending_image_id
        assert c.latest_image_id == first
        await c.on_server_event(s, {'type': 'conversation.item.added', 'item': {'id': second}})
        assert c.latest_image_id == second and c.pending_image_id is None
        assert c.state.snapshot()['visual_last_error'] == ''
        deletes = [m['other_data']['item_id'] for m in messages(s) if m['type'] == 'conversation.item.delete']
        assert deletes == ['stale', first]
        assert not c.stop.is_set()
    asyncio.run(run())


def test_image_rejection_in_raw_and_sdk_events_is_optional_but_audio_errors_remain_fatal(config, tmp_path):
    async def run():
        c = conversation(config, tmp_path, Mock(latest_jpeg=lambda: b'jpeg'))
        s = session()
        await c.refresh_visual_context(s)
        event_id = messages(s)[0]['other_data']['event_id']
        error = {'code': 'invalid_image', 'event_id': event_id}
        await c.on_server_event(s, {'type': 'error', 'error': error, 'event_id': 'server_event'})
        await c.on_event(s, SimpleNamespace(type='error', error=SimpleNamespace(**error)))
        assert not c.failed and not c.stop.is_set()
        assert c.image_accepted.is_set() and c.pending_image_id is None
        await c.on_event(s, SimpleNamespace(type='error', error=RuntimeError('audio failed')))
        assert c.failed and c.stop.is_set()
    asyncio.run(run())


def test_image_upload_failure_does_not_fail_background_task(config, tmp_path):
    async def run():
        c = conversation(config, tmp_path, Mock(latest_jpeg=lambda: b'jpeg'))
        s = session()
        s.model.send_event.side_effect = OSError('upload failed')
        await c.spawn(c.refresh_visual_context(s))
        await asyncio.sleep(0)
        assert not c.failed and not c.stop.is_set()
        assert not c.state.snapshot()['visual_context_pending']
    asyncio.run(run())


def test_direct_microphone_capture_needs_no_rtsp_or_first_video_frame(config):
    state = ready_state()
    state.update(last_frame_at=0, frigate_ready=False)
    supervisor = Mock()
    capture = MediaCapture(config, supervisor, Mock(), state)
    ws = Mock()
    ws.recv.side_effect = [json.dumps({'type':'ready','rate':24000,'channels':1,'format':'pcm16'}),
                           b'\x01\x00'*1200, b'\x02\x00'*1200]
    supervisor.offer_audio.side_effect = lambda _: capture.stopping.set()
    capture._receive_audio(ws)
    supervisor.offer_audio.assert_called_once_with(b'\x01\x00'*1200+b'\x02\x00'*1200)
    assert state.snapshot()['audio_ready'] and not state.snapshot()['video_streaming']
    assert json.loads(ws.send.call_args.args[0])['token'] == config.ebo_api_token


def test_audio_websocket_reconnects_and_stops_without_waking_healthy_source(config):
    capture = MediaCapture(config, Mock(), Mock(), ready_state())
    broken, good = Mock(), Mock()
    capture._audio_connection = Mock(side_effect=[broken, good])
    capture.stopping.wait = Mock(return_value=False)
    def receive(ws):
        if ws is broken:
            raise TimeoutError()
        capture.stopping.set()
    capture._receive_audio = receive
    capture.audio_loop()
    assert capture._audio_connection.call_count == 2
    broken.close.assert_called_once()
    good.close.assert_called_once()
