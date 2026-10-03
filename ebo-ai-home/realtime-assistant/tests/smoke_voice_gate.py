"""Live API test using synthetic speech, no microphone/robot playback/parent data.

Checks both transcript channels and final-transcript-triggered voice generation.
All text/audio artifacts use a temporary directory; summary/memory is disabled.
"""
import asyncio
import json
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from config import Config, Profile
from conversation import Conversation
from ebo_transport import AudioStore, AssistantOutputStore, TranscriptStore
from state import RuntimeState


class SilentSpeaker:
    def __init__(self):self.bytes=0
    def input_muted(self):return False
    def echo_reference(self):return b'',0
    def active_output_id(self):return ''
    def stream_delta(self,pcm,item):self.bytes+=len(pcm)
    def finish_stream(self,pcm,item):pass
    def output_metrics(self,item):return {}


async def main():
    with tempfile.TemporaryDirectory(prefix='ebo-voice-gate-smoke-') as temp:
        directory=Path(temp)
        config=replace(Config.from_env(),profiles=(Profile('test','Test','Test'),),
            instructions='This is a synthetic configuration test. Reply with one short Chinese greeting.',
            visual_enabled=False,memory_root=str(directory/'memory'),
            live_transcript_path=str(directory/'live.jsonl'))
        state=RuntimeState()
        audio=AudioStore(directory/'audio',state)
        speaker=SilentSpeaker()
        c=Conversation(config,config.profiles[0],None,speaker,state,
            TranscriptStore(directory/'gate.jsonl',state,source='gate'),
            AssistantOutputStore(directory/'output.jsonl',audio,state))
        async def no_op(*args):pass
        c.opening=no_op
        c.save_session_memory=no_op
        pcm=subprocess.check_output(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
            'flite=text=Hello please tell me a short story about a friendly robot:voice=slt',
            '-ar','24000','-ac','1','-f','s16le','pipe:1'])
        task=asyncio.create_task(c.run())
        try:
            async def ready():
                while not c.ready.is_set() or not state.snapshot()['live_transcription_configured']:
                    assert not task.done(),state.snapshot()['last_error']
                    await asyncio.sleep(.05)
            await asyncio.wait_for(ready(),25)
            confirmed=state.snapshot()['turn_detection']
            assert confirmed['create_response'] is False and confirmed['interrupt_response'] is False
            # Feed synthetic voice at capture rate, then silence to complete VAD.
            pcm += bytes(48000*2)
            for offset in range(0,len(pcm),4800):
                block=pcm[offset:offset+4800]
                c.offer_audio(block+bytes(4800-len(block)))
                await asyncio.sleep(.1)
            async def complete():
                while (not c.finalized_outputs or not state.snapshot()['live_user_transcripts_received']):
                    assert not task.done(),state.snapshot()['last_error']
                    await asyncio.sleep(.1)
            await asyncio.wait_for(complete(),35)
            snapshot=state.snapshot()
            assert snapshot['manual_responses_requested']==1
            assert speaker.bytes>0 and snapshot['barge_in_count']==0
            assert not c.failed and not snapshot['live_transcription_last_error']
            print(json.dumps({'primary_model':config.input_transcription_model,'live_model':config.live_transcription_model,
                'primary_transcripts':snapshot['user_transcripts_received'],
                'live_transcripts':snapshot['live_user_transcripts_received'],
                'manual_responses':snapshot['manual_responses_requested'],'generated_pcm_bytes':speaker.bytes,
                'automatic_response':False,'automatic_interrupt':False,
                'robot_playback':False,'microphone_capture':False,'parent_memory_written':False}))
        finally:
            c.stop.set()
            await asyncio.wait_for(task,20)


if __name__=='__main__':asyncio.run(main())
