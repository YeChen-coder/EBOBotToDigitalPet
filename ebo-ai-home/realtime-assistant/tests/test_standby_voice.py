import asyncio
import time
import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest
from config import Config, Profile
from conversation import Conversation
from ebo_transport import AudioStore, AssistantOutputStore, Speaker, TranscriptStore
from live_transcription import LiveTranscriber
from runtime import Supervisor
from standby_voice import SpeechSegmenter, StandbyVoice, VoiceTurn, valid_wake_text
from state import RuntimeState
from test_framework import config, conversation, ready_state


class EnergyVAD:
    def is_speech(self, pcm, rate):
        assert rate == 8000 and len(pcm) == 320
        return np.max(np.abs(np.frombuffer(pcm, dtype='<i2'))) > 200


def voice(ms):
    return np.full(ms*24, 2000, dtype='<i2').tobytes()


def test_segmenter_rejects_silence_short_noise_and_never_splits_long_speech():
    s = SpeechSegmenter(EnergyVAD())
    assert s.observe(bytes(48000)) == []
    assert s.observe(voice(100)+bytes(48000)) == []
    chunks = s.observe(voice(500)+bytes(48000))
    assert len(chunks) == 1 and voice(500) in chunks[0]
    assert s.observe(voice(31000)+bytes(48000)) == []
    assert len(s.chunks) == 0
    assert len(s.observe(voice(500)+bytes(48000))) == 1


@pytest.mark.parametrize('text,valid', [('你能看到我吗', True), ('你好', True),
    ('', False), ('嗯', False), ('哈哈', False), ('!!!', False), ('on the.', False)])
def test_wake_requires_meaningful_text(text, valid):
    assert valid_wake_text(text) is valid


def test_echo_and_stale_transcription_cannot_wake():
    eligible = Mock(return_value=False)
    accept = Mock(return_value=True)
    state = RuntimeState()
    wake = StandbyVoice(Config(), state, eligible, accept)
    wake.segmenter = SpeechSegmenter(EnergyVAD())
    wake.offer_audio(voice(500)+bytes(48000))
    assert wake.pending.empty()
    eligible.return_value = True
    wake.offer_audio(voice(500)+bytes(48000))
    turn = wake.pending.get_nowait()
    wake.transcribe = Mock(side_effect=lambda _turn: (wake.reset() or '请讲故事', None))
    assert not wake.process(turn)
    accept.assert_not_called()
    turn = VoiceTurn('stale', voice(500), time.monotonic()-30, wake.epoch)
    assert not wake.process(turn)
    assert wake.transcribe.call_count == 1
    turn = VoiceTurn('fresh', voice(500), time.monotonic(), wake.epoch)
    wake.transcribe = Mock(return_value=('请讲故事', None))
    assert wake.process(turn)
    assert accept.call_args.args[0].text == '请讲故事'
    assert state.snapshot()['voice_wake_accepted'] == 1


def test_supervisor_wakes_without_face_video_or_mqtt_but_never_when_speaker_muted(config):
    state = ready_state()
    state.update(mqtt_connected=False, frigate_ready=False)
    speaker = Mock(input_muted=Mock(return_value=False))
    s = Supervisor(config, state, speaker, Mock(), Mock())
    s.start = Mock(return_value=True)
    turn = VoiceTurn('voice', voice(500), time.monotonic(), 0, '请讲故事')
    assert s.accept_voice(turn)
    s.start.assert_called_once_with('guest', 'voice', turn)
    speaker.input_muted.return_value = True
    assert not s.accept_voice(turn)
    assert s.start.call_count == 1
    speaker.input_muted.return_value = False
    state.update(engine_audio_health={'status': 'muted', 'source_audio_ok': False})
    assert not s.accept_voice(turn)


def test_voice_opening_uses_first_utterance_once_and_guest_never_saves_memory(config, tmp_path):
    async def scenario():
        state = ready_state()
        store = AudioStore(tmp_path/'audio', state)
        speaker = Mock(input_muted=Mock(return_value=False))
        c = Conversation(config, Profile('guest', '', '家人'), None, speaker, state,
            TranscriptStore(tmp_path/'transcripts.jsonl', state),
            AssistantOutputStore(tmp_path/'outputs.jsonl', store, state), 'voice')
        c.ready.set()
        c.live_transcriber = Mock()
        c.initial_turn = VoiceTurn('wake_once', voice(500), time.monotonic(), 0, '请讲故事')
        session = SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()))
        await c.opening(session)
        await asyncio.sleep(.01)
        messages = [call.args[0].message for call in session.model.send_event.call_args_list]
        assert [m['type'] for m in messages] == ['conversation.item.create', 'response.create']
        assert messages[0]['other_data']['item']['content'][0]['text'] == '请讲故事'
        assert c.state.snapshot()['manual_responses_requested'] == 1
        c.live_transcriber.submit_turn.assert_called_once()
        with patch('conversation.summarize_turns', new_callable=AsyncMock) as summarize:
            await c.save_session_memory()
            summarize.assert_not_called()
        assert c.sessions_path is None and not (tmp_path/'memory').exists()
    asyncio.run(scenario())


def test_capture_drops_playback_echo_and_tail_before_queueing(config, tmp_path):
    c = conversation(replace(config, barge_in_enabled=False), tmp_path)
    c.speaker.input_muted.return_value = True
    c.offer_audio(voice(100))
    assert not c.startup_audio and c.audio_queue.empty()
    c.speaker.input_muted.return_value = False
    c.offer_audio(voice(100))
    assert len(c.startup_audio) == 1


def test_live_initial_turn_survives_connection_setup_and_pause_clears_preroll(tmp_path):
    state = RuntimeState()
    live = LiveTranscriber(Config(), state, TranscriptStore(tmp_path/'live.jsonl', state))
    live.observe_audio(b'echo', False)
    live.submit_turn(voice(500))
    assert not live._preroll
    assert live._outgoing.get_nowait() == ('audio', voice(500))
    assert live._outgoing.get_nowait() == ('commit', b'')


def test_speaker_tail_guard_survives_normal_completion_and_explicit_stop(tmp_path):
    speaker = Speaker(Config(), Mock(), AudioStore(tmp_path, RuntimeState()), RuntimeState())
    stream = speaker._new_stream('normal')
    stream.finished.set()
    with patch('ebo_transport.time.monotonic', return_value=100):
        speaker._finalize_stream(stream, 'file', .1)
        assert speaker.input_muted()
    with patch('ebo_transport.time.monotonic', return_value=100.81):
        assert not speaker.input_muted()
    stream = speaker._new_stream('stop')
    stream.finished.set()
    with patch('ebo_transport.time.monotonic', return_value=200):
        speaker.interrupt(b'', 'stop')
        assert speaker.input_muted()
    with patch('ebo_transport.time.monotonic', return_value=200.81):
        assert not speaker.input_muted()


def test_file_transcription_serializes_sdk_language_objects(config):
    wake = StandbyVoice(config, RuntimeState(), lambda: True, Mock())
    wake.client = Mock()
    result = Mock(text='你好', languages=[object()])
    result.model_dump.return_value = {'text': '你好', 'languages': [{'code': 'zh'}]}
    wake.client.audio.transcriptions.create.return_value = result
    turn = VoiceTurn('one', voice(500), time.monotonic(), 0)
    assert wake.transcribe(turn) == ('你好', [{'code': 'zh'}])
    args = wake.client.audio.transcriptions.create.call_args.kwargs
    assert args['model'] == 'gpt-transcribe' and args['file'][1].startswith(b'RIFF')


def test_voice_session_reservation_preserves_first_turn_without_visual_dependencies(config, monkeypatch):
    released = threading.Event()
    class FakeConversation:
        def __init__(self, *args):
            self.profile = args[1]
        async def run(self):
            await asyncio.to_thread(released.wait, 3)
    monkeypatch.setattr('runtime.Conversation', FakeConversation)
    state = ready_state()
    state.update(mqtt_connected=False, frigate_ready=False)
    s = Supervisor(config, state, Mock(input_muted=Mock(return_value=False)), Mock(), Mock())
    turn = VoiceTurn('voice', voice(500), time.monotonic(), 0, '请讲故事')
    try:
        assert s.accept_voice(turn)
        assert s.active.profile.id == 'guest' and s.active.initial_turn is turn
        assert not s.accept_voice(turn) and not s.start('father')
    finally:
        released.set()
        s.worker.join(3)
    assert s.active is None and state.snapshot()['session_state'] == 'standby'


def test_stale_held_face_does_not_select_parent_memory_during_voice_wakeup(config):
    state = ready_state()
    state.update(last_frame_at=time.time()-25)
    s = Supervisor(config, state, Mock(input_muted=Mock(return_value=False)), Mock(), Mock())
    profile = config.profiles[0]
    s.gates[profile.id].tracks['held-face'] = SimpleNamespace(last_seen=time.monotonic(),
        name=profile.face_name, score=1, area=1000000)
    s.start = Mock(return_value=True)
    turn = VoiceTurn('voice', voice(500), time.monotonic(), 0, '你好')
    assert s.accept_voice(turn)
    assert s.start.call_args.args == ('guest','voice',turn)
