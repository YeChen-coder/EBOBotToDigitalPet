"""Real API standby -> validated first utterance -> two transcripts -> one reply.

Uses synthetic speech and a silent speaker. No robot or parental memory writes.
"""
import asyncio
import json
import logging
import subprocess
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from config import Config, Profile
from conversation import Conversation
from ebo_transport import AudioStore, AssistantOutputStore, TranscriptStore
from standby_voice import StandbyVoice, VoiceTurn, valid_wake_text
from state import RuntimeState
from smoke_voice_gate import SilentSpeaker


async def main():
    with tempfile.TemporaryDirectory(prefix='ebo-standby-smoke-') as temp:
        root = Path(temp)
        config = replace(Config.from_env(), visual_enabled=False,
            instructions='This is a synthetic configuration test. Reply with one short Chinese greeting.',
            memory_root=str(root/'memory'), live_transcript_path=str(root/'live.jsonl'))
        state = RuntimeState()
        pcm = subprocess.check_output(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
            'flite=text=Hello please tell me a short story about a friendly robot:voice=slt',
            '-ar', '24000', '-ac', '1', '-f', 's16le', 'pipe:1'])
        wake = StandbyVoice(config, state, lambda: True, lambda turn: True)
        turn = VoiceTurn('wake_smoke', pcm, time.monotonic(), 0)
        try:
            text, languages = await asyncio.to_thread(wake.transcribe, turn)
        finally:
            if wake.client:
                wake.client.close()
        assert valid_wake_text(text, languages), 'standby speech did not pass validation'
        speaker = SilentSpeaker()
        audio = AudioStore(root/'audio', state)
        c = Conversation(config, Profile('guest', '', '家人'), None, speaker, state,
            TranscriptStore(root/'gate.jsonl', state, source='gate'),
            AssistantOutputStore(root/'output.jsonl', audio, state), 'voice')
        c.initial_turn = VoiceTurn(turn.item_id, pcm, turn.captured_at, 0, text, languages)
        task = asyncio.create_task(c.run())
        try:
            async def done():
                while not c.finalized_outputs or not state.snapshot()['live_user_transcripts_received']:
                    assert not task.done(), state.snapshot()['last_error']
                    await asyncio.sleep(.1)
            await asyncio.wait_for(done(), 60)
            snapshot = state.snapshot()
            assert snapshot['manual_responses_requested'] == 1 and speaker.bytes > 0
            assert snapshot['user_transcripts_received'] == 1
            assert not snapshot['live_transcription_last_error'] and not c.failed
            assert snapshot['turn_detection']['interrupt_response'] is False
            print(json.dumps({'standby_transcription_valid': True,
                'primary_transcripts': snapshot['user_transcripts_received'],
                'live_transcripts': snapshot['live_user_transcripts_received'],
                'manual_responses': snapshot['manual_responses_requested'],
                'generated_pcm_bytes': speaker.bytes, 'barge_in_count': snapshot['barge_in_count'],
                'robot_playback': False, 'microphone_capture': False, 'parent_memory_written': False}))
        finally:
            c.stop.set()
            await asyncio.wait_for(task, 20)
            assert not (root/'memory').exists()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
