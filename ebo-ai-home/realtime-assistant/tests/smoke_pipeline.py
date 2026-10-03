"""Opt-in real model voice generation and EBO silent PCM playback, without microphone input.

Generated speech is captured in temporary files and never played on the robot.
Only one second of zero PCM is sent to the actual EBO Engine.
"""
import asyncio
import json
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import Config
from conversation import Conversation
from ebo_transport import AudioStore,AssistantOutputStore,EboAPI,Speaker,TranscriptStore
from state import RuntimeState
from visual import FrigateFrameSource


class CapturedSpeaker:
    def __init__(self,store):
        self.store=store
        self.bytes=0
        self.items=set()
    def input_muted(self):return False
    def echo_reference(self):return b'',0
    def active_output_id(self):return ''
    def stream_delta(self,pcm,item):self.bytes+=len(pcm)
    def finish_stream(self,pcm,item):
        self.store.write_pcm24_wav(pcm,item)
        self.items.add(item)
    def output_metrics(self,item):return {}


async def generate(config,directory):
    state=RuntimeState()
    store=AudioStore(directory/'captured',state)
    speaker=CapturedSpeaker(store)
    c=Conversation(config,config.profiles[0],FrigateFrameSource(config.frigate_url,config.camera_name),speaker,state,
        TranscriptStore(directory/'inputs.jsonl',state),AssistantOutputStore(directory/'outputs.jsonl',store,state))
    task=asyncio.create_task(c.run())
    async def wait():
        while not c.finalized_outputs and not task.done():
            await asyncio.sleep(.1)
        assert c.finalized_outputs and speaker.bytes>0 and not c.failed
        assert state.snapshot()['visual_context_items_added']>0
        assert state.snapshot()['aec_enabled']
    try:
        await asyncio.wait_for(wait(),40)
    finally:
        c.stop.set()
        await asyncio.wait_for(task,15)
    assert not c.memory_turns or all(t['role']=='assistant' for t in c.memory_turns)
    assert not config.memory_paths(config.profiles[0].id)[0].exists()
    return speaker.bytes


def main():
    with tempfile.TemporaryDirectory(prefix='ebo-smoke-') as temp:
        directory=Path(temp)
        config=replace(Config.from_env(),memory_root=str(directory/'memory'))
        count=asyncio.run(generate(config,directory))
        state=RuntimeState()
        speaker=Speaker(config,EboAPI(config,state),AudioStore(directory/'silence',state),state)
        pcm=bytes(48000)
        speaker.stream_delta(pcm,'silent_check')
        speaker.finish_stream(pcm,'silent_check')
        deadline=time.monotonic()+25
        while speaker.input_muted() and time.monotonic()<deadline:
            time.sleep(.05)
        metrics=speaker.output_metrics('silent_check')
        assert metrics.get('streamed') and metrics.get('played_ms',0)>=980
        assert not state.snapshot()['speaker_stream_fallbacks']
        print(json.dumps({'model_voice_pcm_bytes':count,'frigate_context':True,'aec_initialized':True,
            'microphone_sent':False,'parent_memory_written':False,'ebo_silent_played_ms':metrics['played_ms']}))


if __name__=='__main__':main()
