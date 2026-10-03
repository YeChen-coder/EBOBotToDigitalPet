"""Keep SDK VAD observation while giving EBO sole ownership of interruptions.

Agents SDK 0.22.3 emits a playback interrupt on speech_started even with the
server interrupt_response flag disabled. Forward that raw event for observation
without running the SDK's cancel/truncate/playback-reset branch. All other SDK
handling (tools, audio, history, transcription) is retained.
"""
from agents.realtime.openai_realtime import OpenAIRealtimeWebSocketModel, RealtimeModelRawServerEvent


class ClientControlledRealtimeModel(OpenAIRealtimeWebSocketModel):
    async def _handle_ws_event(self, event):
        if event.get('type') == 'input_audio_buffer.speech_started':
            await self._emit_event(RealtimeModelRawServerEvent(data=event))
            return
        await super()._handle_ws_event(event)
