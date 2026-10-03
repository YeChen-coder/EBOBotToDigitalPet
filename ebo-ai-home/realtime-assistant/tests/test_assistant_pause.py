import asyncio
import json
import threading
from dataclasses import replace
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from config import Config
from ebo_transport import AudioStore, Speaker
from runtime import Supervisor, make_http_handler
from session_control import AssistantPreference
from state import RuntimeState
from test_framework import ready_state, conversation


def local_config(tmp_path):
    return replace(Config(), memory_root=str(tmp_path/'memory'), control_token='test-token',
                   live_transcription_enabled=False, proactive_greeting=True)


@pytest.mark.parametrize('session_state', ['standby', 'connecting', 'active', 'saving_memory'])
def test_pause_stops_any_session_and_blocks_every_entry_point(tmp_path, session_state):
    state = ready_state()
    state.update(session_state=session_state)
    speaker = Mock()
    speaker.input_muted.return_value = False
    supervisor = Supervisor(local_config(tmp_path), state, speaker, Mock(), Mock())
    active = Mock()
    if session_state != 'standby':
        supervisor.active = active
    old_epoch = supervisor.wake.epoch
    supervisor.set_enabled(False)
    health = state.snapshot()
    assert health['session_state'] == 'paused' and not health['assistant_enabled']
    assert health['ok'] and health['video_streaming'] and health['audio_streaming']
    assert supervisor.wake.epoch > old_epoch
    assert not supervisor.voice_eligible()
    assert not supervisor.accept_voice(Mock())
    supervisor.offer_audio(b'pcm')
    active.offer_audio.assert_not_called()
    assert active.request_abort.call_count == (session_state != 'standby')
    speaker.suspend.assert_called_once()
    with pytest.raises(ValueError, match='assistant_paused'):
        supervisor.start('father')
    # A recognized face and the periodic presence scan cannot bypass pause.
    supervisor.on_message(None, None, SimpleNamespace(retain=False, topic='frigate/events', payload=json.dumps({
        'type':'new','after':{'id':'face','camera':'ebo','label':'person','area':50000,'sub_label':['爸爸',.99]}}).encode()))
    assert 'face' in supervisor.gates['father'].tracks
    supervisor.consider_present_users()
    assert supervisor.worker is None
    supervisor.set_enabled(True)
    assert state.snapshot()['assistant_enabled']
    speaker.resume.assert_called_once()
    assert supervisor.worker is None  # resuming never replays a saved conversation


def test_pause_is_durable_across_supervisor_restart(tmp_path):
    config = local_config(tmp_path)
    supervisor = Supervisor(config, ready_state(), Mock(), Mock(), Mock())
    supervisor.set_enabled(False)
    restarted = Supervisor(config, ready_state(), Mock(), Mock(), Mock())
    assert not restarted.enabled
    assert restarted.state.snapshot()['session_state'] == 'paused'
    restarted.set_enabled(True)
    assert Supervisor(config, ready_state(), Mock(), Mock(), Mock()).enabled


def test_unreadable_preference_does_not_unexpectedly_enable_ai(tmp_path):
    path = tmp_path/'assistant-control.json'
    path.write_text('{broken', encoding='utf-8')
    preference = AssistantPreference(path)
    assert preference.load() is False
    assert preference.error
    preference.save(True)
    assert preference.load() is True and not preference.error


def test_pause_api_authentication_and_manual_start_denial(tmp_path):
    config = local_config(tmp_path)
    state = ready_state()
    supervisor = Supervisor(config, state, Mock(), Mock(), Mock())
    server = ThreadingHTTPServer(('127.0.0.1',0), make_http_handler(Mock(directory=tmp_path), state, supervisor, config))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    def post(path, body=b'{}', token='test-token'):
        return urlopen(Request(f'http://127.0.0.1:{server.server_port}'+path, data=body,
                              headers={'X-EBO-Control-Token':token}, method='POST'))
    try:
        with pytest.raises(HTTPError) as error:
            post('/assistant/pause', token='wrong')
        assert error.value.code == 403 and supervisor.enabled
        with post('/assistant/pause') as result:
            assert json.load(result) == {'accepted':True,'assistant_enabled':False}
        with pytest.raises(HTTPError) as error:
            post('/session/start', b'{"user_id":"father"}')
        assert error.value.code == 409
        assert json.load(error.value)['error'] == 'assistant_paused'
        with post('/assistant/resume') as result:
            assert json.load(result)['assistant_enabled']
    finally:
        server.shutdown(); server.server_close(); worker.join(2)


@pytest.mark.parametrize('stage', ['before_run', 'runner', 'enter', 'active'])
def test_pause_aborts_connection_or_active_session_without_goodbye_or_summary(tmp_path, monkeypatch, stage):
    async def scenario():
        c = conversation(local_config(tmp_path), tmp_path)
        reached = asyncio.Event()
        never = asyncio.Event()
        session = SimpleNamespace(enter=AsyncMock(), close=AsyncMock())
        async def runner_run(**kwargs):
            if stage == 'runner':
                reached.set()
                await never.wait()
            return session
        runner = Mock(run=AsyncMock(side_effect=runner_run))
        monkeypatch.setattr('conversation.RealtimeRunner', lambda *a, **k:runner)
        async def enter():
            if stage == 'enter':
                reached.set()
                await never.wait()
        session.enter.side_effect = enter
        async def ongoing(*args):
            reached.set()
            await never.wait()
        for name in ['opening','consume_events','microphone','playback_progress','speaker_output','watchdog']:
            setattr(c, name, AsyncMock(side_effect=ongoing))
        c.save_session_memory = AsyncMock()
        if stage == 'before_run':
            c.request_abort()
            await c.run()
            runner.run.assert_not_called()
        else:
            task = asyncio.create_task(c.run())
            await asyncio.wait_for(reached.wait(), 2)
            c.request_abort()
            await asyncio.wait_for(task, 2)
            if stage in {'enter','active'}:
                session.close.assert_awaited_once()
        c.save_session_memory.assert_not_called()
        assert c.stop.is_set()
    asyncio.run(scenario())


def test_speaker_pause_blocks_late_audio_and_old_fallback_after_resume(tmp_path):
    state = RuntimeState()
    ebo = Mock()
    speaker = Speaker(Config(playback_tail_ms=0), ebo, AudioStore(tmp_path,state), state)
    speaker.stream_delta(b'\0\0'*100, 'old')  # not enough PCM to start a worker
    old = speaker._stream
    old.failed = 'network interrupted'
    old.finished.set()
    speaker.suspend()
    assert old.interrupted and old.stop_requested.is_set()
    assert not speaker.input_muted()  # a prebuffered response cannot wedge resume
    speaker.stream_delta(b'pcm', 'late')
    speaker.finish_stream(b'pcm', 'late')
    speaker.play(b'pcm', 'late')
    ebo.command.assert_not_called()  # idle/stream pause never globally stops a family call
    speaker.resume()
    speaker._finalize_stream(old, 'reply-old.wav', .1)
    speaker._play_url('reply-old.wav', .1, generation=old.generation)
    ebo.command.assert_not_called()
    speaker.play(b'\0\0'*100, 'new')
    assert ebo.command.call_args.args[0] == 'talk'


def test_pause_stops_assistant_owned_url_playback(tmp_path):
    state = RuntimeState()
    ebo = Mock()
    speaker = Speaker(Config(), ebo, AudioStore(tmp_path,state), state)
    speaker.play(b'\0\0'*100, 'old')
    ebo.command.reset_mock()
    speaker.suspend()
    ebo.command.assert_called_once_with('talk/stop')


def test_pause_tolerates_worker_finishing_at_the_same_time(tmp_path):
    c = conversation(local_config(tmp_path), tmp_path)
    c.loop = asyncio.new_event_loop()
    c.loop.close()
    c.request_abort()
    assert c.abort_requested.is_set()


def test_pause_cancels_session_summary_already_in_progress(tmp_path, monkeypatch):
    async def scenario():
        c = conversation(local_config(tmp_path), tmp_path)
        c.loop = asyncio.get_running_loop()
        c.memory_turns = [{'role':'user','text':'Remember my preference.'}]
        reached = asyncio.Event()
        async def summarize(*args, **kwargs):
            reached.set()
            await asyncio.Event().wait()
        monkeypatch.setattr('conversation.summarize_turns', summarize)
        c.memory_task = asyncio.create_task(c.save_session_memory())
        await asyncio.wait_for(reached.wait(), 1)
        c.request_abort()
        with pytest.raises(asyncio.CancelledError):
            await c.memory_task
        assert not c.state.snapshot()['memory_pending']
    asyncio.run(scenario())


def test_pause_cancels_background_memory_consolidation(tmp_path, monkeypatch):
    supervisor = Supervisor(local_config(tmp_path), ready_state(), Mock(), Mock(), Mock())
    reached = threading.Event()
    async def consolidate(*args, **kwargs):
        reached.set()
        await asyncio.Event().wait()
    monkeypatch.setattr('runtime.consolidation_due', lambda *args:True)
    monkeypatch.setattr('runtime.consolidate_memory', consolidate)
    worker = threading.Thread(target=supervisor.memory_loop, daemon=True)
    worker.start()
    try:
        assert reached.wait(2)
        supervisor.set_enabled(False)
        supervisor.stopping.set()
        worker.join(2)
        assert not worker.is_alive()
        assert not supervisor.state.snapshot()['memory_pending']
    finally:
        supervisor.stopping.set()


def test_stream_pause_stops_audio_already_sent_and_waiting_for_playback(tmp_path, monkeypatch):
    import websocket
    speaker = Speaker(Config(), Mock(), AudioStore(tmp_path,RuntimeState()), RuntimeState())
    stream = speaker._new_stream('queued')
    stream.chunks.put(None)
    messages = []
    class Socket:
        ready = False
        def send(self, payload):
            message = json.loads(payload)
            messages.append(message['type'])
            if message['type'] == 'end':
                speaker.suspend()  # all PCM was sent; the robot is still playing
        def recv(self):
            if not self.ready:
                self.ready = True
                return '{"type":"ready"}'
            if 'stop' in messages:
                return '{"type":"stopped"}'
            raise websocket.WebSocketTimeoutException()
        def settimeout(self, timeout): pass
        def close(self): pass
    monkeypatch.setattr('ebo_transport.websocket.create_connection', lambda *a, **k:Socket())
    speaker._stream_worker(stream)
    assert messages == ['start','end','stop']
    assert stream.finished.is_set() and stream.interrupted
