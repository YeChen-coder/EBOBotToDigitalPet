import asyncio
import json
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from config import Config, Profile
from conversation import Conversation
from ebo_transport import AudioStore, AssistantOutputStore, EboAPI, Speaker, TranscriptStore
from state import RuntimeState
from session_memory import realtime_memory_context, save_memory
from visual import VisualUnavailable


def ready_state():
    state = RuntimeState()
    now = time.time()
    state.update(listener_ready=True, session_state='standby', frigate_ready=True, mqtt_connected=True,
        engine_audio_monitor_enabled=True, engine_audio_checked_at=now,
        engine_audio_health={'observed_at':now,'last_packet_at':now,'last_pcm_at':now,'status':'receiving','source_audio_ok':True})
    state.mark_media('frame')
    state.mark_media('audio')
    return state


@pytest.fixture
def config(tmp_path):
    return replace(Config(), openai_api_key='test-key', ebo_api_token='token', control_token='token', memory_root=str(tmp_path/'memory'))


def conversation(config, tmp_path, frame_source=None):
    state = ready_state()
    state.update(active_user='father',session_started_at=time.time())
    store = AudioStore(tmp_path/'replies', state)
    transcripts = TranscriptStore(tmp_path/'transcripts.jsonl',state)
    outputs = AssistantOutputStore(tmp_path/'outputs.jsonl',store,state)
    speaker = Mock()
    speaker.input_muted.return_value = False
    speaker.output_metrics.return_value = {}
    speaker.active_output_id.return_value = ''
    return Conversation(config,config.profile('father'),frame_source,speaker,state,transcripts,outputs)


def test_standby_is_healthy_but_actual_source_failure_is_not():
    state = ready_state()
    assert state.snapshot()['ok'] and not state.snapshot()['realtime_connected']
    for status in ('muted','no_source_packets','no_decoded_pcm','disconnected'):
        state.update(engine_audio_health={**state.snapshot()['engine_audio_health'],'status':status,'source_audio_ok':False})
        assert not state.snapshot()['ok']
    state.update(session_state='active', realtime_connected=False)
    assert not state.snapshot()['ok']


def test_video_staleness_and_mqtt_disconnect_remain_visible_without_blocking_audio():
    state = ready_state()
    state.update(last_frame_at=time.time()-35)
    assert not state.snapshot()['video_streaming']
    state.mark_media('frame')
    state.update(mqtt_connected=False)
    assert state.snapshot()['ok']


def test_video_source_health_overrides_frigate_held_frame_fps():
    state = ready_state()
    now = time.time()
    state.update(engine_video_monitor_enabled=True, engine_video_checked_at=now,
                 engine_video_health={'observed_at':now,'last_frame_at':now,
                                      'status':'receiving','source_video_ok':True})
    assert state.snapshot()['ok']
    state.update(engine_video_health={'observed_at':now,'last_frame_at':now-25,
                                     'status':'receiving','source_video_ok':True})
    health = state.snapshot()
    assert health['frigate_ready'] and not health['video_streaming'] and health['ok']
    assert health['transport_media_ok'] and health['source_audio_ok']
    assert health['source_video_status'] == 'source_stale'
    state.update(engine_video_health={'observed_at':now-25,'last_frame_at':now,
                                     'status':'receiving','source_video_ok':True})
    assert state.snapshot()['source_video_status'] == 'monitor_stale'


def test_server_response_and_interrupt_are_disabled_with_local_gate_config(monkeypatch,tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    monkeypatch.setenv('EBO_API_TOKEN','token')
    monkeypatch.setenv('EBO_MEMORY_ROOT',str(tmp_path))
    monkeypatch.setenv('REALTIME_VAD_CREATE_RESPONSE','false')
    monkeypatch.setenv('REALTIME_INPUT_NOISE_REDUCTION','off')
    monkeypatch.setenv('EBO_BARGE_IN_CONFIRM_MS','400')
    config = Config.from_env()
    settings = config.session_settings()['audio']['input']
    assert settings['turn_detection']['create_response'] is False
    assert settings['turn_detection']['interrupt_response'] is False
    assert config.barge_in_confirm_ms==400
    assert settings['noise_reduction']=={'type':'far_field'}


def test_memory_is_empty_initially_and_isolated_by_parent(config):
    father = config.memory_paths('father')
    mother = config.memory_paths('mother')
    assert realtime_memory_context(*father)=='' and realtime_memory_context(*mother)==''
    save_memory(father[0],'one','Father likes tea.')
    assert 'Father likes tea.' in realtime_memory_context(*father)
    assert realtime_memory_context(*mother)==''
    with pytest.raises(ValueError):
        config.memory_paths('../father')


def test_duplicate_profile_or_path_traversal_is_rejected(config):
    with pytest.raises(ValueError):
        replace(config,profiles=(Profile('../father','爸爸','爸爸'),)).validate()
    with pytest.raises(ValueError):
        replace(config,profiles=(config.profiles[0],config.profiles[0])).validate()


def test_images_wait_for_ack_delete_previous_and_never_request_reply(config,tmp_path):
    async def scenario():
        c = conversation(config,tmp_path,Mock(latest_jpeg=lambda:b'jpeg'))
        session = SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()))
        await c.refresh_visual_context(session)
        first = c.pending_image_id
        assert first and c.latest_image_id is None
        await c.on_server_event(session,{'type':'conversation.item.added','item':{'id':first}})
        await c.refresh_visual_context(session)
        second = c.pending_image_id
        assert c.latest_image_id == first
        events = [x.args[0].message for x in session.model.send_event.call_args_list]
        assert not any(x['type']=='response.create' for x in events)
        assert not any(x['type']=='conversation.item.delete' for x in events)
        await c.on_server_event(session,{'type':'conversation.item.added','item':{'id':second}})
        assert session.model.send_event.call_args.args[0].message['other_data']['item_id']==first
    asyncio.run(scenario())


def test_unavailable_frame_removes_stale_visual_context(config,tmp_path):
    async def scenario():
        c = conversation(config,tmp_path,Mock(latest_jpeg=Mock(side_effect=VisualUnavailable('offline'))))
        c.latest_image_id='old'
        session=SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()))
        await c.refresh_visual_context(session)
        assert c.latest_image_id is None
        assert session.model.send_event.call_args.args[0].message['type']=='conversation.item.delete'
    asyncio.run(scenario())


def test_final_transcripts_are_deduplicated_and_validated(config,tmp_path):
    c = conversation(config,tmp_path)
    assert c.accept_transcript('user1','你好') is True
    assert c.accept_transcript('user1','你好') is False
    rows=[json.loads(x) for x in c.transcripts.path.read_text().splitlines()]
    assert len(rows)==1 and rows[0]['source']=='realtime' and rows[0]['user_id']=='father'
    assert c.memory_turns==[{'role':'user','text':'你好'}]


def test_real_sdk_raw_event_conversion_and_audio_before_completion(config,tmp_path):
    from agents.realtime.openai_realtime import _ConversionHelper
    async def scenario():
        c=conversation(config,tmp_path)
        worker=asyncio.create_task(c.speaker_output())
        session=SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()))
        await c.send_raw(session,'conversation.item.delete',item_id='old')
        assert _ConversionHelper.try_convert_raw_message(session.model.send_event.call_args.args[0]).item_id=='old'
        await c.on_event(session,SimpleNamespace(type='raw_model_event',data=SimpleNamespace(type='turn_started',response_id='response')))
        await c.on_event(session,SimpleNamespace(type='audio',item_id='item',content_index=0,audio=SimpleNamespace(data=b'\0\0'*2400)))
        await asyncio.sleep(.01)
        c.speaker.stream_delta.assert_called_once()
        c.speaker.finish_stream.assert_not_called()
        await c.on_server_event(session,{'type':'response.output_audio_transcript.done','item_id':'item','transcript':'回答','response_id':'response'})
        await c.on_server_event(session,{'type':'response.output_audio.done','item_id':'item'})
        await asyncio.sleep(.01)
        c.speaker.finish_stream.assert_called_once()
        assert len(c.outputs.path.read_text().splitlines())==1
        assert json.loads(c.outputs.path.read_text())['response_id']=='response'
        assert 'item' not in c.output_pcm
        worker.cancel()
        await asyncio.gather(worker,return_exceptions=True)
    asyncio.run(scenario())


def test_only_confirmed_local_interruption_stops_engine_and_deduplicates_output(config,tmp_path):
    from speech_gate import BargeInDecision
    async def scenario():
        c=conversation(config,tmp_path)
        c.playback_item='item'
        c.output_pcm['item']=bytearray(b'\0\0'*2400)
        c.output_text['item']='回答'
        c.speaker.interrupt.return_value={'interrupted':True,'played_ms':30,'generated_ms':100}
        session=SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()),send_audio=AsyncMock())
        await c.on_event(None,SimpleNamespace(type='audio_interrupted'))
        c.speaker.interrupt.assert_not_called()
        assert c.state.snapshot()['barge_in_count']==0
        await c.handle_barge_in(session,BargeInDecision(True,b'\0\0'*1200,300,.1,.8))
        c.speaker.interrupt.assert_called_once()
        assert c.state.snapshot()['barge_in_count']==1
        assert json.loads(c.outputs.path.read_text())['interrupted'] is True
        await c.on_server_event(None,{'type':'response.output_audio.done','item_id':'item'})
        assert len(c.outputs.path.read_text().splitlines())==1
    asyncio.run(scenario())


def test_pcm_is_24khz_mono_and_persisted_without_deletion(tmp_path):
    import wave
    state=RuntimeState()
    store=AudioStore(tmp_path,state)
    name,duration=store.write_pcm24_wav(b'\0\0'*24000,'response')
    assert duration==1
    with wave.open(str(tmp_path/name),'rb') as audio:
        assert (audio.getframerate(),audio.getnchannels(),audio.getsampwidth())==(24000,1,2)
    assert (tmp_path/name).exists()


def test_aec_uses_same_specter_processor_and_100ms_frames():
    import numpy as np
    from pywebrtc_audio import AudioProcessor
    processor=AudioProcessor(sample_rate=24000,echo_cancellation=True,noise_suppression=True,auto_gain_control=False,stream_delay_ms=0)
    samples=np.zeros(2400,dtype=np.int16)
    assert processor.process(samples,samples).shape==samples.shape
