"""Local standby segmentation; only completed speech reaches transcription."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import io
import logging
import queue
import re
import threading
import time
import uuid
import wave

import numpy as np
import webrtcvad
from speech_gate import actionable_transcript

LOG = logging.getLogger('ebo-standby-voice')


@dataclass(frozen=True)
class VoiceTurn:
    item_id: str
    pcm: bytes
    captured_at: float
    epoch: int
    text: str = ''
    languages: object = None


def valid_wake_text(text, languages=None):
    compact = ''.join(re.findall(r'[\w\u4e00-\u9fff]', text or '')).lower()
    return (len(compact) >= 2 and compact not in {'嗯嗯', '啊啊', '哦哦', '呃呃', '喵喵', '哈哈', '呵呵'}
            and actionable_transcript(text, languages))


class SpeechSegmenter:
    """24 kHz PCM -> bounded utterances, with silence and short noises rejected."""
    def __init__(self, vad=None):
        self.vad = vad or webrtcvad.Vad(2)
        self.reset()

    def reset(self):
        self.preroll = deque(maxlen=15)  # 300 ms, 20 ms frames
        self.chunks = []
        self.voiced = self.silence = 0
        self.too_long = False

    def observe(self, pcm):
        results = []
        for offset in range(0, len(pcm)-959, 960):
            frame = pcm[offset:offset+960]
            downsampled = np.frombuffer(frame, dtype='<i2')[::3].tobytes()
            voiced = self.vad.is_speech(downsampled, 8000)
            if not self.chunks:
                self.preroll.append(frame)
                if not voiced:
                    continue
                self.chunks = list(self.preroll)
                self.preroll.clear()
            else:
                if not self.too_long:
                    self.chunks.append(frame)
            self.voiced += int(voiced)
            self.silence = 0 if voiced else self.silence+1
            # Do not answer in the middle of a long utterance. Drop oversized
            # candidates and resume listening after silence, rather than splitting.
            if len(self.chunks) >= 1500:  # 30 seconds maximum retained PCM
                self.too_long = True
            if self.silence >= 35:  # 700 ms end-of-turn silence
                if self.voiced >= 15 and not self.too_long:
                    results.append(b''.join(self.chunks))
                self.reset()
        return results


class StandbyVoice:
    def __init__(self, config, state, eligible, accept):
        self.config, self.state = config, state
        self.eligible, self.accept = eligible, accept
        self.segmenter = SpeechSegmenter()
        self.lock = threading.Lock()
        self.epoch = 0
        self.pending = queue.Queue(maxsize=2)
        self.stopping = threading.Event()
        self.client = None
        state.update(voice_wake_enabled=config.voice_wake_enabled)

    def reset(self):
        with self.lock:
            self.epoch += 1
            self.segmenter.reset()
        while True:
            try:
                self.pending.get_nowait()
            except queue.Empty:
                break
        self.state.update(voice_wake_listening=False)

    def offer_audio(self, pcm):
        if not self.config.voice_wake_enabled or not self.eligible():
            self.reset()
            return
        self.state.update(voice_wake_listening=True)
        with self.lock:
            for audio in self.segmenter.observe(pcm):
                turn = VoiceTurn('wake_'+uuid.uuid4().hex[:24], audio, time.monotonic(), self.epoch)
                try:
                    self.pending.put_nowait(turn)
                    self.state.increment('voice_wake_candidates')
                except queue.Full:
                    self.state.increment('voice_wake_rejected')

    def transcribe(self, turn):
        from openai import OpenAI
        if self.client is None:
            self.client = OpenAI(api_key=self.config.openai_api_key, timeout=15, max_retries=0)
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(turn.pcm)
        options = {}
        for key in ('keywords', 'language', 'languages', 'prompt'):
            value = getattr(self.config, 'input_transcription_'+key)
            if value:
                options[key] = list(value) if isinstance(value, tuple) else value
        result = self.client.audio.transcriptions.create(
            file=('standby.wav', buffer.getvalue(), 'audio/wav'),
            model=self.config.input_transcription_model, **options)
        return result.text, result.model_dump(mode='json').get('languages')

    def process(self, turn):
        if turn.epoch != self.epoch or not self.eligible() or time.monotonic()-turn.captured_at > 20:
            self.state.increment('voice_wake_rejected')
            return False
        self.state.update(voice_wake_transcribing=True)
        try:
            text, languages = self.transcribe(turn)
            self.state.update(voice_wake_last_error='')
            if (turn.epoch != self.epoch or not self.eligible()
                    or time.monotonic()-turn.captured_at > 20
                    or not valid_wake_text(text, languages)):
                self.state.increment('voice_wake_rejected')
                return False
            verified = VoiceTurn(turn.item_id, turn.pcm, turn.captured_at, turn.epoch, text.strip(), languages)
            if self.accept(verified):
                self.state.increment('voice_wake_accepted')
                self.state.update(last_voice_wake_at=time.time())
                LOG.info('validated standby voice opened a conversation: item=%s', turn.item_id)
                return True
            self.state.increment('voice_wake_rejected')
        except Exception as exc:
            self.state.update(voice_wake_last_error=type(exc).__name__)
            LOG.warning('standby transcription failed: %s', type(exc).__name__)
        finally:
            self.state.update(voice_wake_transcribing=False)
        return False

    def run(self):
        try:
            while not self.stopping.is_set():
                try:
                    turn = self.pending.get(timeout=.2)
                except queue.Empty:
                    continue
                self.process(turn)
        finally:
            if self.client:
                self.client.close()

    def stop(self):
        self.stopping.set()
        self.reset()
