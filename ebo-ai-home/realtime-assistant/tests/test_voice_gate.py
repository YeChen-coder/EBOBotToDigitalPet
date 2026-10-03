import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest
from speech_gate import BargeInGate, BargeInDecision, actionable_transcript
from live_transcription import LiveTranscriber
from realtime_model import ClientControlledRealtimeModel
from agents.realtime.openai_realtime import OpenAIRealtimeWebSocketModel
from config import Config
from ebo_transport import TranscriptStore
from state import RuntimeState
from test_framework import conversation, config


class EnergySpeech:
    def is_speech(self, pcm, rate):
        return np.sqrt(np.mean(np.frombuffer(pcm, dtype='<i2').astype(float)**2)) > 200


def test_original_gate_rejects_robot_echo_and_short_noise_then_accepts_independent_voice():
    rng = np.random.default_rng(42)
    reference = rng.integers(-9000, 9000, 24000, dtype=np.int16)
    gate = BargeInGate(vad=EnergySpeech())
    echo = reference[-7200:].tobytes()
    decision = gate.observe(echo, reference.tobytes(), 1000)
    assert not decision.triggered and decision.echo_correlation > .99
    assert decision.residual_ratio < .01
    gate.reset()
    assert not gate.observe(echo[:4800], b'', 0).triggered
    gate.reset()
    voice = rng.integers(-9000, 9000, 12000, dtype=np.int16).tobytes()
    decision = gate.observe(voice, reference.tobytes(), 1000)
    assert decision.triggered and decision.preroll == voice
    assert not gate.observe(voice, reference.tobytes(), 1000).triggered


@pytest.mark.parametrize('text,languages,expected', [
    ('',None,False), ('on the.',None,False), ('Maola, okay, maola.',None,False),
    ('猫猫帮我看看',None,True), ('药盒在2楼',None,True),
    ('ni hao',[{'code':'zh'}],True), ('Could you tell me a story?',None,True),
])
def test_previous_final_transcript_filter(text, languages, expected):
    assert actionable_transcript(text,languages) is expected


def test_sdk_vad_is_observation_only_without_cancel_truncate_or_tracker_reset():
    async def scenario():
        model = ClientControlledRealtimeModel()
        model._emit_event = AsyncMock()
        model._cancel_response = AsyncMock()
        model._playback_tracker = Mock()
        event = {'type':'input_audio_buffer.speech_started','item_id':'user','audio_start_ms':100}
        with patch.object(OpenAIRealtimeWebSocketModel, '_handle_ws_event', new_callable=AsyncMock) as base:
            await model._handle_ws_event(event)
            base.assert_not_called()
            model._emit_event.assert_awaited_once()
            assert model._emit_event.call_args.args[0].data == event
            assert model._emit_event.call_args.args[0].type == 'raw_server_event'
            model._cancel_response.assert_not_called()
            model._playback_tracker.on_interrupted.assert_not_called()
            await model._handle_ws_event({'type':'response.done'})
            base.assert_awaited_once()
    asyncio.run(scenario())


def test_empty_foreign_noise_never_replies_and_one_validated_turn_replies_once(config,tmp_path):
    async def scenario():
        c=conversation(config,tmp_path)
        session=SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()))
        await c.on_server_event(session,{'type':'conversation.item.input_audio_transcription.completed',
            'item_id':'noise','transcript':'on the.'})
        await asyncio.sleep(.01)
        session.model.send_event.assert_not_called()
        await c.on_server_event(session,{'type':'conversation.item.input_audio_transcription.completed',
            'item_id':'user','transcript':'你能看到我吗'})
        await c.on_event(session,SimpleNamespace(type='raw_model_event',data=SimpleNamespace(
            type='input_audio_transcription_completed',item_id='user',transcript='你能看到我吗')))
        await asyncio.sleep(.01)
        events=[call.args[0].message['type'] for call in session.model.send_event.call_args_list]
        assert events == ['response.create']
        assert c.state.snapshot()['manual_responses_requested'] == 1
        assert len(c.transcripts.path.read_text().splitlines()) == 2
    asyncio.run(scenario())


def test_validated_input_waits_for_previous_playback(config,tmp_path):
    async def scenario():
        c=conversation(config,tmp_path)
        c.speaker.input_muted.return_value=True
        session=SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()))
        await c.on_server_event(session,{'type':'conversation.item.input_audio_transcription.completed',
            'item_id':'user','transcript':'继续讲'})
        await asyncio.sleep(.02)
        session.model.send_event.assert_not_called()
        c.speaker.input_muted.return_value=False
        await asyncio.sleep(.06)
        assert session.model.send_event.call_count == 1
    asyncio.run(scenario())


def test_confirmed_local_interrupt_cancels_truncates_and_replays_opening_once(config,tmp_path):
    async def scenario():
        c=conversation(config,tmp_path)
        c.response_active=True
        c.response_id='response'
        c.playback_item='output'
        c.speaker.active_output_id.return_value='output'
        c.output_pcm['output']=bytearray(b'\0\0'*24000)
        c.output_text['output']='回答'
        c.speaker.interrupt.return_value={'played_ms':400,'generated_ms':1000,'interrupted':True}
        session=SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()),send_audio=AsyncMock())
        pcm=b'\0\0'*12000
        await c.handle_barge_in(session,BargeInDecision(True,pcm,300,.1,.8))
        events=[call.args[0].message for call in session.model.send_event.call_args_list]
        assert [x['type'] for x in events] == ['response.cancel','conversation.item.truncate','input_audio_buffer.clear']
        assert events[1]['other_data']['audio_end_ms'] == 400
        session.send_audio.assert_awaited_once_with(pcm)
        assert c.locally_interrupted and c.state.snapshot()['barge_in_count']==1
        await c.on_event(session,SimpleNamespace(type='audio_interrupted',item_id='output'))
        assert c.state.snapshot()['barge_in_count']==1
    asyncio.run(scenario())


def test_playback_audio_is_not_sent_to_either_transcriber(config,tmp_path):
    async def scenario():
        c=conversation(replace(config,aec_enabled=False,barge_in_enabled=False),tmp_path)
        c.ready.set()
        c.speaker.input_muted.return_value=True
        c.speaker.echo_reference.return_value=(b'',0)
        c.live_transcriber=Mock()
        session=SimpleNamespace(send_audio=AsyncMock())
        worker=asyncio.create_task(c.microphone(session))
        c.audio_queue.put_nowait(b'\0\0'*2400)
        await asyncio.sleep(.01)
        session.send_audio.assert_not_called()
        c.live_transcriber.pause_audio.assert_called_once_with()
        worker.cancel()
        await asyncio.gather(worker,return_exceptions=True)
    asyncio.run(scenario())


def test_live_channel_retains_original_model_settings_and_never_requests_response(tmp_path):
    state=RuntimeState()
    state.update(active_user='mother',session_started_at=100)
    store=TranscriptStore(tmp_path/'live.jsonl',state,source='live')
    live=LiveTranscriber(Config(),state,store)
    settings=live._session_update()
    assert settings['session']['type']=='transcription'
    assert settings['session']['audio']['input']['turn_detection'] is None
    assert settings['session']['audio']['input']['transcription']=={
        'model':'gpt-live-transcribe','delay':'low','languages':('zh',)}
    live._ready.set()
    live.observe_audio(b'a'*4800,False)
    live.observe_audio(b'b'*4800,True)
    live.observe_audio(b'c'*4800,True)
    live.observe_audio(b'',False)
    entries=[]
    while not live._outgoing.empty():entries.append(live._outgoing.get_nowait())
    assert [k for k,_ in entries]==['audio','audio','audio','commit']
    assert live.user_id=='mother' and live.session_started_at==100
    state.update(active_user='father',session_started_at=200)
    store.append('late','妈妈的记录',session_started_at=live.session_started_at,user_id=live.user_id)
    record=json.loads(store.path.read_text())
    assert record['user_id']=='mother' and record['session_started_at']==100


def test_restored_transcription_settings_and_server_flags(monkeypatch,tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY','test')
    monkeypatch.setenv('EBO_API_TOKEN','test')
    monkeypatch.setenv('EBO_MEMORY_ROOT',str(tmp_path))
    monkeypatch.setenv('REALTIME_VAD_INTERRUPT_RESPONSE','true')
    monkeypatch.setenv('REALTIME_VAD_CREATE_RESPONSE','true')
    monkeypatch.setenv('OPENAI_INPUT_TRANSCRIPTION_LANGUAGE','zh')
    monkeypatch.setenv('OPENAI_INPUT_TRANSCRIPTION_KEYWORDS_JSON','["猫猫"]')
    settings=Config.from_env().session_settings()['audio']['input']
    assert settings['transcription']['language']=='zh'
    assert settings['transcription']['keywords']==['猫猫']
    assert settings['turn_detection']['interrupt_response'] is False
    assert settings['turn_detection']['create_response'] is False
