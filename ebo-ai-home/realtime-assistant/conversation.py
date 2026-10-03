"""Specter-style finite voice sessions, with EBO replacing PortAudio playback.

Final primary transcripts own responses; local voice/echo gates own interruption.
Frigate images retain the current single-frame acknowledgment/replacement flow.
"""
from __future__ import annotations
import asyncio
import base64
import logging
import time
import uuid
import threading
from collections import deque
from pathlib import Path
from typing import Any

from agents import function_tool
from agents.realtime import RealtimeAgent, RealtimeModelSendRawMessage, RealtimePlaybackTracker, RealtimeRunner
from prompt import agent_instructions
from research import make_research_tool
from session_control import explicit_close_phrase
from session_memory import realtime_memory_context, save_memory, summarize_turns
from visual import VisualUnavailable
from speech_gate import BargeInGate, actionable_transcript
from live_transcription import LiveTranscriber
from ebo_transport import TranscriptStore
from realtime_model import ClientControlledRealtimeModel

LOG = logging.getLogger('ebo-conversation')


class Conversation:
    def __init__(self, config, profile, frame_source, speaker, state, transcripts, outputs, trigger='manual'):
        self.config, self.profile, self.frame_source = config, profile, frame_source
        self.speaker, self.state, self.transcripts, self.outputs = speaker, state, transcripts, outputs
        self.trigger = trigger
        self.initial_turn = None
        self.startup_audio = deque(maxlen=100)
        self.startup_lock = threading.Lock()
        self.local_session_id = uuid.uuid4().hex
        self.started = self.last_activity = time.monotonic()
        self.stop = asyncio.Event()
        self.abort_requested = threading.Event()
        self.connect_task = self.memory_task = None
        self.ready = asyncio.Event()
        self.initial_turn_staged = asyncio.Event()
        self.initial_turn_staged.set()
        self.opening_complete = asyncio.Event()
        self.opening_complete.set()
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self.playback_queue = asyncio.Queue()
        self.received_audio_done = set()
        self.playback_tracker = RealtimePlaybackTracker()
        self.response_active = False
        self.response_requested = False
        self.locally_interrupted = False
        self.cancelled_response_ids = set()
        self.pending_response_items = []
        self.response_gate_task = None
        self.live_transcriber = None
        self.live_thread = None
        self.barge_gate = BargeInGate(confirm_ms=config.barge_in_confirm_ms,
            preroll_ms=config.barge_in_preroll_ms, vad_mode=config.barge_in_vad_mode,
            echo_correlation=config.barge_in_echo_correlation, residual_ratio=config.barge_in_residual_ratio)
        self.tools_in_progress = 0
        self.microphone_speaking = False
        self.pending_transcriptions = 0
        self.close_requested_at = None
        self.voice_close_requested_at = None
        self.explicit_close_at = None
        self.goodbye_generated = False
        self.memory_turns = []
        self.completed_input_items = set()
        self.partial_user_transcripts = {}
        self.pending_image_id = None
        self.pending_image_at = 0
        self.latest_image_id = None
        self.visual_lock = asyncio.Lock()
        self.visual_fetch_task = None
        self.visual_events = deque(maxlen=64)
        self.visual_timeout = 2.0
        self.image_accepted = asyncio.Event()
        self.response_id = ''
        self.output_pcm: dict[str, bytearray] = {}
        self.output_text: dict[str, str] = {}
        self.output_response: dict[str, str] = {}
        self.output_content: dict[str, int] = {}
        self.finalized_outputs = set()
        self.audio_ended = set()
        self.remembered_assistant_items = set()
        self.interrupted_outputs = set()
        self.playback_item = ''
        self.playback_ms = 0
        self.reference_cursor = 0
        self.playback_started = None
        self.processor = None
        self.loop = None
        self.background_tasks = set()
        self.failed = False
        self.sessions_path, self.long_term_path = (config.memory_paths(profile.id)
            if profile.id != 'guest' else (None, None))

    @staticmethod
    async def send_raw(session: Any, kind: str, **fields):
        await session.model.send_event(RealtimeModelSendRawMessage(message={'type': kind, 'other_data': fields}))

    def offer_audio(self, pcm):
        # The capture thread never blocks waiting for OpenAI. Drop stale input under backpressure.
        if self.stop.is_set():
            return
        if not self.config.barge_in_enabled and (self.response_active or self.speaker.input_muted()):
            return
        def offer():
            if self.stop.is_set():
                return
            if self.audio_queue.full():
                self.audio_queue.get_nowait()
            self.audio_queue.put_nowait(pcm)
        try:
            with self.startup_lock:
                if self.loop is None:
                    self.startup_audio.append(pcm)
                else:
                    self.loop.call_soon_threadsafe(offer)
        except RuntimeError:
            pass

    def request_close(self):
        if self.loop:
            self.loop.call_soon_threadsafe(self._request_close)
        else:
            self._request_close()

    def _request_close(self):
        self.close_requested_at = time.monotonic()

    def request_abort(self):
        """Pause immediately, including during connection and memory saving."""
        self.abort_requested.set()
        if self.loop:
            try:
                self.loop.call_soon_threadsafe(self._abort)
            except RuntimeError:
                pass  # the worker may have just finished and closed its loop
        else:
            self._abort()

    def _abort(self):
        self.stop.set()
        for task in (self.connect_task, self.memory_task):
            if task is not None:
                task.cancel()

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.background_tasks.add(task)
        def complete(done):
            self.background_tasks.discard(done)
            if not done.cancelled() and done.exception():
                self.failed = True
                self.state.update(last_error=f'session_task:{type(done.exception()).__name__}')
                self.stop.set()
        task.add_done_callback(complete)
        return task

    async def refresh_visual_context(self, session):
        if self.frame_source is None:
            return
        async with self.visual_lock:
            try:
                await self._refresh_visual_context(session)
            except Exception as exc:
                # Images are optional. HTTP/decode/upload failures cannot stop
                # opening, microphone processing, or validated voice replies.
                self.state.update(visual_last_error=type(exc).__name__)
                LOG.warning('Visual context unavailable: %s', type(exc).__name__)
                await self._clear_visual_context(session)

    async def send_visual(self, session, kind, **fields):
        event_id = 'visual_' + uuid.uuid4().hex
        item_id = fields.get('item_id') or fields.get('item', {}).get('id')
        self.visual_events.append((event_id, item_id))
        await asyncio.wait_for(self.send_raw(session, kind, event_id=event_id, **fields), timeout=1)

    def visual_error(self, error):
        event_id = error.get('event_id') if isinstance(error, dict) else getattr(error, 'event_id', None)
        if not event_id:
            return False
        match = next((item for event, item in self.visual_events if event == event_id), None)
        if match is None:
            return False
        if match == self.pending_image_id:
            self.pending_image_id = None
            self.image_accepted.set()
            self.state.update(visual_context_pending=False)
        self.state.update(visual_last_error='image_rejected')
        return True

    async def _clear_visual_context(self, session):
        ids = {self.pending_image_id, self.latest_image_id} - {None}
        self.pending_image_id = self.latest_image_id = None
        self.image_accepted.set()
        self.state.update(visual_context_pending=False)
        for item_id in ids:
            try:
                await self.send_visual(session, 'conversation.item.delete', item_id=item_id)
            except Exception:
                pass

    async def _refresh_visual_context(self, session):
        if self.pending_image_id:
            if time.monotonic()-self.pending_image_at < 5:
                return
            # A missing acknowledgment must not block image updates indefinitely.
            await self.send_visual(session, 'conversation.item.delete', item_id=self.pending_image_id)
            self.pending_image_id = None
            self.state.update(visual_context_pending=False)
        try:
            # One fetch per conversation, including after a timeout. A stuck
            # HTTP worker must not create an unbounded queue of new workers.
            if self.visual_fetch_task is not None and not self.visual_fetch_task.done():
                raise VisualUnavailable('Previous image fetch is still running')
            if self.visual_fetch_task is not None:
                # Retrieve a late failure but discard the old picture.
                try:
                    self.visual_fetch_task.result()
                except Exception:
                    pass
            self.visual_fetch_task = asyncio.create_task(asyncio.to_thread(self.frame_source.latest_jpeg))
            jpeg = await asyncio.wait_for(asyncio.shield(self.visual_fetch_task), timeout=self.visual_timeout)
        except VisualUnavailable as exc:
            self.state.update(visual_last_error=type(exc).__name__)
            await self._clear_visual_context(session)
            return
        item_id = 'img_' + uuid.uuid4().hex[:28]
        self.pending_image_id = item_id
        self.pending_image_at = time.monotonic()
        self.image_accepted.clear()
        self.state.update(visual_context_pending=True)
        try:
            await self.send_visual(session, 'conversation.item.create', item={
                'id': item_id, 'type': 'message', 'role': 'user',
                'content': [{'type': 'input_image', 'image_url': 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode('ascii')}],
            })
        except Exception:
            raise

    async def opening(self, session):
        await asyncio.wait_for(self.ready.wait(), timeout=20)
        turn = self.initial_turn
        accepted = False
        try:
            self.initial_turn = None
            if turn is not None:
                # Preserve the first utterance before subsequent microphone input.
                await self.send_raw(session, 'conversation.item.create', item={
                    'id': turn.item_id, 'type': 'message', 'role': 'user',
                    'content': [{'type': 'input_text', 'text': turn.text}]})
                if self.live_transcriber:
                    self.live_transcriber.submit_turn(turn.pcm)
                accepted = self.accept_transcript(turn.item_id, turn.text, turn.languages, completes_audio=False)
            self.initial_turn_staged.set()
            await self.refresh_visual_context(session)
            if self.pending_image_id:
                try:
                    await asyncio.wait_for(self.image_accepted.wait(), timeout=3)
                except asyncio.TimeoutError:
                    pass
            if turn is not None:
                if accepted:
                    self.queue_validated_response(session, turn.item_id)
                return
            if (not self.microphone_speaking and not self.pending_transcriptions and not self.pending_response_items
                    and not self.response_active and not self.response_requested and not self.stop.is_set()):
                self.response_requested = True
                await self.send_raw(session, 'response.create', response={'output_modalities': ['audio'],
                    'instructions': f'{self.profile.display_name}开始了这次对话。只用一句简短自然的中文问候，不描述画面、不自我介绍，然后停下来聆听。'})
        finally:
            self.opening_complete.set()

    def accept_transcript(self, item_id, transcript, languages=None, *, completes_audio=True):
        if item_id in self.completed_input_items:
            return False
        if item_id:
            self.completed_input_items.add(item_id)
            self.partial_user_transcripts.pop(item_id, None)
        if completes_audio:
            self.pending_transcriptions = max(0, self.pending_transcriptions-1)
        text = transcript.strip() if isinstance(transcript, str) else ''
        self.transcripts.append(item_id or uuid.uuid4().hex, text, languages)
        if text:
            self.last_activity = time.monotonic()
            self.memory_turns.append({'role': 'user', 'text': text})
        if explicit_close_phrase(text):
            self.explicit_close_at = time.monotonic()
        if not actionable_transcript(text, languages):
            self.state.increment('input_turns_ignored')
            LOG.info('voice gate ignored empty/low-information input: item=%s', item_id)
            return False
        return True

    def queue_validated_response(self, session, item_id):
        self.pending_response_items.append(item_id)
        if self.response_gate_task is None or self.response_gate_task.done():
            self.response_gate_task = self.spawn(self.respond_to_validated_turns(session))

    async def respond_to_validated_turns(self, session):
        # Serialize manual response.create against opening, generation, tools and
        # actual Engine playback. Multiple already-accepted fragments share a reply.
        def busy():
            return (not self.opening_complete.is_set() or self.response_requested or self.response_active or self.tools_in_progress
                    or self.speaker.input_muted() or not self.playback_queue.empty()
                    or not self.audio_queue.empty() or self.microphone_speaking or self.pending_transcriptions)
        while self.pending_response_items and not self.stop.is_set():
            if busy():
                await asyncio.sleep(.05)
                continue
            # A frame fetch is in flight before pending_image_id is assigned.
            # Wait for it before checking the server's image acknowledgment.
            async with self.visual_lock:
                pass
            if busy():
                continue
            if self.pending_image_id:
                try:
                    await asyncio.wait_for(self.image_accepted.wait(), timeout=3)
                except asyncio.TimeoutError:
                    pass
                if busy() or self.visual_lock.locked():
                    continue
            if self.stop.is_set():
                return
            items = self.pending_response_items[:]
            self.pending_response_items.clear()
            self.response_requested = True
            await self.send_raw(session, 'response.create')
            self.state.increment('manual_responses_requested')
            LOG.info('voice gate requested response: input_items=%s', ','.join(str(x) for x in items))

    async def handle_barge_in(self, session, decision):
        """Only the restored local voice/echo gate can cancel/truncate playback."""
        if not decision.triggered:
            return
        item = self.speaker.active_output_id() or self.playback_item
        active_response = self.response_active
        response_id = self.response_id
        if not item and not active_response:
            return
        self.locally_interrupted = True
        if active_response and response_id:
            self.cancelled_response_ids.add(response_id)
        while not self.playback_queue.empty():
            _, queued_item, _ = self.playback_queue.get_nowait()
            self.interrupted_outputs.add(queued_item)
        metrics = {}
        if item:
            self.interrupted_outputs.add(item)
            metrics = await asyncio.to_thread(self.speaker.interrupt, bytes(self.output_pcm.get(item, b'')), item)
            self.outputs.update_stream_metadata(item, metrics)
            self._persist_output(item, metrics)
        if active_response:
            await self.send_raw(session, 'response.cancel', **({'response_id': response_id} if response_id else {}))
        played = int(metrics.get('played_ms', 0))
        generated = int(metrics.get('generated_ms', 0))
        if item and generated > played:
            await self.send_raw(session, 'conversation.item.truncate', item_id=item,
                content_index=self.output_content.get(item, 0), audio_end_ms=played)
        self.playback_tracker.on_interrupted()
        self.playback_item, self.reference_cursor, self.playback_started = '', 0, None
        self.state.increment('barge_in_count')
        self.state.update(last_barge_in_at=time.time(), last_barge_in_speech_ms=decision.speech_ms,
            last_barge_in_echo_correlation=decision.echo_correlation, last_barge_in_residual_ratio=decision.residual_ratio)
        LOG.info('local barge-in confirmed: item=%s speech=%dms echo=%.3f residual=%.3f played=%dms',
            item, decision.speech_ms, decision.echo_correlation, decision.residual_ratio, played)
        # Preserve the beginning of the user's utterance once, after clearing
        # stale uncommitted microphone input. Wait for response.done before replying.
        await self.send_raw(session, 'input_audio_buffer.clear')
        await session.send_audio(decision.preroll)
        if self.live_transcriber:
            self.live_transcriber.observe_audio(decision.preroll, True)

    async def on_event(self, session, event):
        kind = event.type
        if kind == 'audio':
            item = event.item_id
            if item in self.interrupted_outputs:
                return
            pcm = event.audio.data
            self.output_pcm.setdefault(item, bytearray()).extend(pcm)
            self.output_response[item] = self.response_id
            self.output_content[item] = event.content_index
            self.playback_queue.put_nowait(('delta', item, pcm))
            self.last_activity = time.monotonic()
            return
        if kind == 'audio_interrupted':
            # Defensive guard: VAD/SDK events must never stop EBO directly.
            LOG.info('ignored SDK audio interruption: item=%s', getattr(event, 'item_id', None))
            return
        if kind in {'tool_start', 'tool_end'}:
            self.tools_in_progress = max(0, self.tools_in_progress + (1 if kind == 'tool_start' else -1))
            self.state.update(tools_in_progress=self.tools_in_progress)
            self.last_activity = time.monotonic()
            return
        if kind == 'error':
            if self.visual_error(event.error):
                return
            self.state.update(last_error=f'realtime_sdk:{type(event.error).__name__}')
            self.failed = True
            self.stop.set()
            return
        if kind != 'raw_model_event':
            return
        raw = event.data
        if raw.type == 'turn_started':
            self.response_requested = False
            self.response_active = True
            self.response_id = raw.response_id
            self.last_activity = time.monotonic()
        elif raw.type == 'turn_ended':
            self.response_active = False
            self.last_activity = time.monotonic()
        elif raw.type == 'input_audio_transcription_completed':
            if self.accept_transcript(raw.item_id, raw.transcript):
                self.queue_validated_response(session, raw.item_id)
        elif raw.type == 'raw_server_event':
            await self.on_server_event(session, raw.data)

    async def on_server_event(self, session, data):
        kind = data.get('type')
        if kind == 'session.updated':
            received = data.get('session', {}).get('audio', {}).get('input', {})
            self.state.update(realtime_connected=True, session_state='active',
                input_transcription_configured=bool(received.get('transcription')),
                input_noise_reduction=received.get('noise_reduction'), turn_detection=received.get('turn_detection', {}))
            self.ready.set()
        elif kind in {'conversation.item.added', 'conversation.item.created'}:
            item = data.get('item', {}).get('id')
            if item and item == self.pending_image_id:
                previous = self.latest_image_id
                self.latest_image_id, self.pending_image_id = item, None
                self.image_accepted.set()
                self.state.increment('visual_context_items_added')
                self.state.update(last_visual_context_at=time.time(), visual_context_pending=False, visual_last_error='')
                if previous and previous != item:
                    try:
                        await self.send_visual(session, 'conversation.item.delete', item_id=previous)
                    except Exception as exc:
                        self.state.update(visual_last_error=type(exc).__name__)
        elif kind in {'input_audio_buffer.speech_started', 'input_audio_buffer.speech_stopped'}:
            self.microphone_speaking = kind.endswith('speech_started')
            self.state.update(input_speech_active=self.microphone_speaking)
            self.last_activity = time.monotonic()
            LOG.info('voice gate VAD: event=%s item=%s playback=%s', kind, data.get('item_id'), self.playback_item)
            if self.microphone_speaking:
                self.spawn(self.refresh_visual_context(session))
            else:
                self.pending_transcriptions += 1
                if self.live_transcriber:
                    self.live_transcriber.pause_audio()
        elif kind == 'conversation.item.input_audio_transcription.completed':
            if self.accept_transcript(data.get('item_id'), data.get('transcript'), data.get('languages')):
                self.queue_validated_response(session, data.get('item_id'))
        elif kind == 'conversation.item.input_audio_transcription.delta':
            item, delta = data.get('item_id'), data.get('delta')
            if isinstance(item, str) and isinstance(delta, str):
                self.partial_user_transcripts[item] = (self.partial_user_transcripts.get(item, '') + delta)[:4000]
        elif kind == 'conversation.item.input_audio_transcription.failed':
            self.pending_transcriptions = max(0, self.pending_transcriptions-1)
            self.state.update(last_error='input_transcription_failed')
        elif kind == 'response.created':
            self.locally_interrupted = False
            self.response_requested = False
            self.response_active = True
            self.response_id = data.get('response', {}).get('id', '')
        elif kind == 'response.done':
            self.response_active = False
            response = data.get('response', {})
            LOG.info('response finished: id=%s status=%s details=%s', response.get('id'),
                response.get('status'), response.get('status_details'))
        elif kind == 'response.output_audio.delta':
            if data.get('response_id') in self.cancelled_response_ids:
                self.interrupted_outputs.add(data.get('item_id'))
        elif kind == 'response.output_audio.done':
            item = data.get('item_id')
            if item and item not in self.received_audio_done:
                self.received_audio_done.add(item)
                if item not in self.interrupted_outputs:
                    self.playback_queue.put_nowait(('done', item, None))
                else:
                    self.audio_ended.add(item)
                    self._persist_output(item)
        elif kind in {'response.output_audio_transcript.done', 'response.output_text.done'}:
            item = data.get('item_id')
            text = data.get('transcript') or data.get('text') or ''
            self.output_text[item] = text
            self.output_response[item] = data.get('response_id', self.response_id)
            if text.strip() and item not in self.remembered_assistant_items:
                self.memory_turns.append({'role': 'assistant', 'text': text.strip()})
                self.remembered_assistant_items.add(item)
                if self.voice_close_requested_at:
                    self.goodbye_generated = True
            self._persist_output(item)
        elif kind == 'error':
            code = data.get('error', {}).get('code', 'unknown')
            if self.visual_error(data.get('error', {})):
                return
            elif code != 'response_cancel_not_active':
                self.state.update(last_error='realtime_event_error')
                self.failed = True
                self.stop.set()

    def _persist_output(self, item, metrics=None):
        if not item or item in self.finalized_outputs or item not in self.output_text:
            return
        if item not in self.audio_ended and item not in self.interrupted_outputs:
            return
        self.outputs.append(item, self.output_response.get(item, ''), item, self.output_text[item],
            metrics or self.speaker.output_metrics(item))
        self.finalized_outputs.add(item)
        # Prevent accumulated raw PCM from growing throughout a long session.
        self.output_pcm.pop(item, None)

    async def microphone(self, session):
        await asyncio.wait_for(self.ready.wait(), timeout=20)
        await asyncio.wait_for(self.initial_turn_staged.wait(), timeout=20)
        if self.config.aec_enabled:
            from pywebrtc_audio import AudioProcessor
            self.processor = AudioProcessor(sample_rate=24000, echo_cancellation=True,
                noise_suppression=True, auto_gain_control=False, stream_delay_ms=self.config.aec_delay_ms)
            self.state.update(aec_enabled=True)
        while not self.stop.is_set():
            pcm = await self.audio_queue.get()
            if self.close_requested_at or self.voice_close_requested_at or self.tools_in_progress:
                continue
            raw_pcm = pcm
            reference, played_ms = self.speaker.echo_reference()
            if self.processor is not None:
                import numpy as np
                end = min(len(reference), played_ms * 48)
                available = reference[self.reference_cursor:end]
                reference_pcm = available[:len(pcm)] + bytes(max(0, len(pcm)-len(available)))
                self.reference_cursor = min(end, self.reference_cursor+len(pcm))
                pcm = self.processor.process(np.frombuffer(pcm, dtype=np.int16), np.frombuffer(reference_pcm, dtype=np.int16)).tobytes()
            speaking = (self.speaker.input_muted() or self.response_active) and not self.locally_interrupted
            if speaking:
                if self.live_transcriber:
                    self.live_transcriber.pause_audio()
                if self.playback_started and (time.monotonic()-self.playback_started)*1000 < self.config.aec_warmup_ms:
                    self.barge_gate.reset()
                    continue
                if self.config.barge_in_enabled:
                    decision = self.barge_gate.observe(raw_pcm, reference, played_ms)
                    if decision.triggered:
                        await self.handle_barge_in(session, decision)
                continue
            self.barge_gate.reset()
            await session.send_audio(pcm)
            if self.live_transcriber:
                self.live_transcriber.observe_audio(pcm, self.microphone_speaking)

    async def playback_progress(self):
        while not self.stop.is_set():
            await asyncio.sleep(.05)
            item = self.playback_item
            if not item:
                continue
            metrics = self.speaker.output_metrics(item)
            played = int(metrics.get('played_ms', 0))
            if played > self.playback_ms:
                self.playback_tracker.on_play_ms(item, self.output_content.get(item, 0), played-self.playback_ms)
                self.playback_ms = played
                self.last_activity = time.monotonic()
            if not self.response_active and not self.speaker.input_muted():
                self.outputs.update_stream_metadata(item, metrics)
                self.playback_tracker.on_interrupted()
                self.playback_item, self.playback_started, self.reference_cursor = '', None, 0

    async def speaker_output(self):
        # Specter's playback queue retains every chunk and serializes utterances.
        # Engine status determines when a previous utterance has actually finished.
        while not self.stop.is_set() and not self.abort_requested.is_set():
            kind, item, pcm = await self.playback_queue.get()
            if self.abort_requested.is_set() or item in self.interrupted_outputs:
                continue
            if kind == 'delta':
                if self.playback_item != item:
                    while self.speaker.input_muted() and not self.stop.is_set():
                        await asyncio.sleep(.05)
                    if self.stop.is_set() or item in self.interrupted_outputs:
                        continue
                    self.playback_tracker.on_interrupted()
                    self.playback_item, self.playback_ms, self.reference_cursor = item, 0, 0
                    self.playback_started = time.monotonic()
                self.speaker.stream_delta(pcm, item)
            else:
                self.speaker.finish_stream(bytes(self.output_pcm.get(item, b'')), item)
                self.audio_ended.add(item)
                self._persist_output(item)

    async def consume_events(self, session):
        try:
            async for event in session:
                await self.on_event(session, event)
        finally:
            self.stop.set()

    async def watchdog(self):
        while not self.stop.is_set():
            await asyncio.sleep(.2)
            now = time.monotonic()
            busy = self.response_requested or self.pending_response_items or self.response_active or self.speaker.input_muted() or not self.playback_queue.empty() or self.tools_in_progress or self.microphone_speaking or self.pending_transcriptions
            if self.close_requested_at and ((not self.microphone_speaking and not self.pending_transcriptions) or now-self.close_requested_at > 15):
                self.stop.set()
            elif self.voice_close_requested_at and ((self.goodbye_generated and not busy) or now-self.voice_close_requested_at > 12):
                self.stop.set()
            elif self.explicit_close_at and not self.voice_close_requested_at and now-self.explicit_close_at > 3:
                self.stop.set()
            elif now-self.started >= self.config.session_max_seconds or (self.ready.is_set() and not busy and now-self.last_activity >= self.config.session_idle_seconds):
                self.stop.set()
            elif not self.ready.is_set() and now-self.started > 25:
                self.failed = True
                self.state.update(last_error='session_configuration_timeout')
                self.stop.set()

    async def save_session_memory(self):
        if self.profile.id == 'guest':
            self.state.update(memory_pending=False, memory_status='no_memory')
            return
        for item, text in self.partial_user_transcripts.items():
            if item not in self.completed_input_items and text.strip():
                self.memory_turns.append({'role': 'user', 'text': '[Incomplete transcription] ' + text.strip()})
        if not any(t['role'] == 'user' for t in self.memory_turns):
            return
        self.state.update(memory_pending=True, memory_status='summarizing')
        try:
            summary = await summarize_turns(self.memory_turns, tracing_disabled=not self.config.trace_enabled)
            if summary != 'NO_MEMORY':
                save_memory(self.sessions_path, self.local_session_id, summary)
                self.state.update(memory_status='saved', memory_last_saved_at=time.time(), memory_last_error='')
            else:
                self.state.update(memory_status='no_memory')
        except Exception as exc:
            self.state.update(memory_status='failed', memory_last_error=type(exc).__name__)
            LOG.warning('Session memory failed: %s', type(exc).__name__)
        finally:
            self.state.update(memory_pending=False)

    async def run(self):
        if self.abort_requested.is_set():
            return
        self.opening_complete.clear()
        if self.initial_turn is not None:
            self.initial_turn_staged.clear()
        with self.startup_lock:
            self.loop = asyncio.get_running_loop()
            for pcm in self.startup_audio:
                self.audio_queue.put_nowait(pcm)
            self.startup_audio.clear()
        self.state.update(session_state='connecting', active_user=self.profile.id, session_id=self.local_session_id,
            session_started_at=time.time(), session_trigger=self.trigger, last_error='')
        try:
            memory = (realtime_memory_context(self.sessions_path, self.long_term_path, max_chars=self.config.memory_max_chars)
                      if self.sessions_path is not None else '')
        except (OSError, ValueError) as exc:
            memory = ''
            self.state.update(memory_status='failed', memory_last_error=type(exc).__name__)
        self.state.update(memory_context_chars=len(memory))
        # Bound method tools are built per instance, so the SDK never exposes self in its schema.
        @function_tool
        async def end_conversation() -> str:
            """Close this conversation when the family member asks to stop listening."""
            self.voice_close_requested_at = time.monotonic()
            return '正在关闭本次会话。现在只说一句简短的中文道别，然后停止。'
        agent = RealtimeAgent(name='EBO family assistant', instructions=agent_instructions(self.config, self.profile, memory),
            tools=[make_research_tool(self.config), end_conversation])
        runner = RealtimeRunner(agent, model=ClientControlledRealtimeModel(),
            config={'model_settings': self.config.session_settings(), 'tracing_disabled': not self.config.trace_enabled})
        if self.abort_requested.is_set():
            return
        self.connect_task = asyncio.ensure_future(runner.run(model_config={'playback_tracker': self.playback_tracker}))
        try:
            session = await asyncio.wait_for(self.connect_task, timeout=20)
        except asyncio.CancelledError:
            if self.abort_requested.is_set():
                return
            raise
        finally:
            self.connect_task = None
        try:
            if self.abort_requested.is_set():
                return
            self.connect_task = asyncio.ensure_future(session.enter())
            try:
                await asyncio.wait_for(self.connect_task, timeout=20)
            except asyncio.CancelledError:
                if self.abort_requested.is_set():
                    return
                raise
            finally:
                self.connect_task = None
            if self.abort_requested.is_set():
                return
            if self.config.live_transcription_enabled:
                import threading
                self.live_transcriber = LiveTranscriber(self.config, self.state,
                    TranscriptStore(Path(self.config.live_transcript_path), self.state, source='live'))
                self.live_thread = threading.Thread(target=self.live_transcriber.run, name='ebo-live-transcription', daemon=True)
                self.live_thread.start()
            self.spawn(self.consume_events(session))
            async def initialize_opening():
                try:
                    await self.opening(session)
                finally:
                    self.opening_complete.set()
            self.spawn(initialize_opening())
            self.spawn(self.microphone(session))
            self.spawn(self.playback_progress())
            self.spawn(self.speaker_output())
            self.spawn(self.watchdog())
            await self.stop.wait()
        finally:
            for task in list(self.background_tasks):
                task.cancel()
            await asyncio.gather(*list(self.background_tasks), return_exceptions=True)
            if self.live_transcriber:
                self.live_transcriber.stop()
                await asyncio.to_thread(self.live_thread.join, 3)
            try:
                await asyncio.wait_for(session.close(), timeout=10)
            except Exception as exc:
                LOG.warning('Session close failed: %s', type(exc).__name__)
            if not self.abort_requested.is_set() and (self.speaker.active_output_id() or (self.state.snapshot()['speaker_stream_status'] in {'fallback', 'url'}
                    and self.speaker.input_muted())):
                item = self.speaker.active_output_id()
                await asyncio.to_thread(self.speaker.interrupt, bytes(self.output_pcm.get(item, b'')), item)
            self.state.update(realtime_connected=False, session_state='saving_memory', input_speech_active=False,
                tools_in_progress=0, aec_enabled=False, visual_context_pending=False)
            if not self.abort_requested.is_set():
                self.memory_task = asyncio.create_task(self.save_session_memory())
                try:
                    await self.memory_task
                except asyncio.CancelledError:
                    if not self.abort_requested.is_set():
                        raise
                finally:
                    self.memory_task = None
