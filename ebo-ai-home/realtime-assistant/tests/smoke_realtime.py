"""Opt-in live SDK config and Frigate-image acceptance check, with no microphone or speech."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agents.realtime import RealtimeAgent,RealtimeRunner,RealtimePlaybackTracker
from config import Config
from conversation import Conversation
from realtime_model import ClientControlledRealtimeModel
from prompt import agent_instructions
from research import make_research_tool
from visual import FrigateFrameSource


async def main():
    config=Config.from_env()
    runner=RealtimeRunner(RealtimeAgent(name='EBO silent connection check',
        instructions=agent_instructions(config,config.profiles[0],''),tools=[make_research_tool(config)]),
        model=ClientControlledRealtimeModel(), config={'model_settings':config.session_settings(),'tracing_disabled':True})
    session=await runner.run(model_config={'playback_tracker':RealtimePlaybackTracker()})
    seen={}
    try:
        await asyncio.wait_for(session.enter(),20)
        async def events():
            async for event in session:
                if event.type=='error':
                    raise RuntimeError(type(event.error).__name__)
                if event.type!='raw_model_event' or event.data.type!='raw_server_event':
                    continue
                data=event.data.data
                if data.get('type')=='session.updated' and not seen:
                    input_config=data['session']['audio']['input']
                    seen['automatic_vad_response']=input_config['turn_detection']['create_response']
                    seen['automatic_vad_interrupt']=input_config['turn_detection']['interrupt_response']
                    seen['noise_reduction']=input_config.get('noise_reduction')
                    seen['transcription_model']=input_config['transcription']['model']
                    seen['prompt_retained']=data['session']['instructions'].startswith(config.instructions)
                    frame=await asyncio.to_thread(FrigateFrameSource(config.frigate_url,config.camera_name).latest_jpeg)
                    import base64
                    await Conversation.send_raw(session,'conversation.item.create',item={'id':'img_ebo_silent_smoke','type':'message','role':'user',
                        'content':[{'type':'input_image','image_url':'data:image/jpeg;base64,'+base64.b64encode(frame).decode('ascii')}]})
                elif data.get('type') in {'conversation.item.added','conversation.item.created'} and data.get('item',{}).get('id')=='img_ebo_silent_smoke':
                    seen['frigate_image_accepted']=True
                    await Conversation.send_raw(session,'conversation.item.delete',item_id='img_ebo_silent_smoke')
                    return
                elif data.get('type')=='error':
                    raise RuntimeError(data.get('error',{}).get('code','realtime_error'))
        await asyncio.wait_for(events(),30)
        assert seen.get('frigate_image_accepted') and seen.get('prompt_retained')
        assert seen['automatic_vad_response'] is False and seen['automatic_vad_interrupt'] is False
        print(json.dumps(seen))
    finally:
        await asyncio.wait_for(session.close(),10)


if __name__=='__main__':
    asyncio.run(main())
