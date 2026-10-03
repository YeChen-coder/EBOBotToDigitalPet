import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from standby_voice import VoiceTurn
from test_framework import config, conversation


def event_types(session):
    return [call.args[0].message['type'] for call in session.model.send_event.call_args_list]


def test_reply_waits_for_frame_fetch_and_acceptance(config, tmp_path):
    async def scenario():
        entered, release = threading.Event(), threading.Event()
        def jpeg():
            entered.set()
            release.wait(2)
            return b'jpeg'
        c = conversation(config, tmp_path, Mock(latest_jpeg=jpeg))
        session = SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()))
        frame = asyncio.create_task(c.refresh_visual_context(session))
        try:
            await asyncio.to_thread(entered.wait, 1)
            await c.on_server_event(session, {'type': 'conversation.item.input_audio_transcription.completed',
                'item_id': 'question', 'transcript': '我手里拿的是什么'})
            await asyncio.sleep(.02)
            assert 'response.create' not in event_types(session)
            release.set()
            await frame
            await asyncio.sleep(.02)
            assert 'response.create' not in event_types(session)
            await c.on_server_event(session, {'type': 'conversation.item.added',
                'item': {'id': c.pending_image_id}})
            await asyncio.sleep(.06)
            assert event_types(session).count('response.create') == 1
        finally:
            release.set()
            await asyncio.gather(frame, return_exceptions=True)
            for task in list(c.background_tasks):
                task.cancel()
            await asyncio.gather(*list(c.background_tasks), return_exceptions=True)
    asyncio.run(scenario())


def test_first_wake_text_precedes_frame_fetch_and_does_not_complete_next_audio(config, tmp_path):
    async def scenario():
        c = conversation(config, tmp_path)
        c.ready.set()
        c.initial_turn = VoiceTurn('wake_one', b'pcm', time.monotonic(), 0, '讲个故事')
        c.pending_transcriptions = 1  # A following microphone utterance is still transcribing.
        c.live_transcriber = Mock()
        session = SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()))
        async def refresh(_session):
            messages = [call.args[0].message for call in session.model.send_event.call_args_list]
            assert messages[0]['other_data']['item']['id'] == 'wake_one'
        c.refresh_visual_context = refresh
        await c.opening(session)
        await asyncio.sleep(.01)
        assert c.pending_transcriptions == 1
        assert 'response.create' not in event_types(session)
        assert c.initial_turn_staged.is_set()
        for task in list(c.background_tasks):
            task.cancel()
        await asyncio.gather(*list(c.background_tasks), return_exceptions=True)
    asyncio.run(scenario())


def test_new_audio_while_waiting_for_image_ack_delays_reply(config, tmp_path):
    async def scenario():
        c = conversation(config, tmp_path, Mock(latest_jpeg=lambda: b'jpeg'))
        session = SimpleNamespace(model=SimpleNamespace(send_event=AsyncMock()))
        await c.refresh_visual_context(session)
        await c.on_server_event(session, {'type': 'conversation.item.input_audio_transcription.completed',
            'item_id': 'first', 'transcript': '帮我看看这个'})
        await asyncio.sleep(.01)
        await c.on_server_event(session, {'type': 'input_audio_buffer.speech_stopped'})
        assert c.pending_transcriptions == 1
        await c.on_server_event(session, {'type': 'conversation.item.added',
            'item': {'id': c.pending_image_id}})
        await asyncio.sleep(.06)
        assert 'response.create' not in event_types(session)
        await c.on_server_event(session, {'type': 'conversation.item.input_audio_transcription.completed',
            'item_id': 'second', 'transcript': '我说的是我手里的东西'})
        await asyncio.sleep(.06)
        assert event_types(session).count('response.create') == 1
    asyncio.run(scenario())
