"""Independent live transcript; never creates or interrupts assistant responses."""
from __future__ import annotations
import base64
from collections import deque
import json
import logging
import queue
import threading
import time
import websocket
from config import Config
from state import RuntimeState
from ebo_transport import TranscriptStore

LOG = logging.getLogger('ebo-live-transcription')

class LiveTranscriber:
    """Transcribe the same microphone turns independently of the reply gate."""

    def __init__(self, config: Config, state: RuntimeState, store: TranscriptStore) -> None:
        self.config = config
        self.state = state
        self.store = store
        snapshot = state.snapshot()
        self.user_id = snapshot.get('active_user')
        self.session_started_at = snapshot['realtime_session_started_at']
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._reset = threading.Event()
        self._outgoing: queue.Queue[tuple[str, bytes]] = queue.Queue(maxsize=200)
        self._preroll: deque[bytes] = deque(maxlen=12)
        self._feeding = False
        self._ws: websocket.WebSocket | None = None

    def stop(self) -> None:
        self._stop.set()
        self._ready.clear()
        ws = self._ws
        if ws is not None:
            ws.close()

    def observe_audio(self, pcm: bytes, speaking: bool) -> None:
        """Called only by the capture thread; keep silence out of the second API stream."""
        if pcm:
            self._preroll.append(pcm)
        if not self._ready.is_set():
            self._feeding = False
            return
        if speaking:
            if not self._feeding:
                for chunk in self._preroll:
                    self._enqueue("audio", chunk)
                self._feeding = True
            elif pcm:
                self._enqueue("audio", pcm)
        elif self._feeding:
            self._enqueue("commit", b"")
            self._feeding = False
            self._preroll.clear()

    def pause_audio(self):
        if self._feeding:
            self._enqueue('commit', b'')
        self._feeding = False
        self._preroll.clear()

    def submit_turn(self, pcm):
        # A validated standby utterance is retained even during connection setup.
        self.pause_audio()
        self._enqueue('audio', pcm)
        self._enqueue('commit', b'')

    def _enqueue(self, kind: str, payload: bytes) -> None:
        try:
            self._outgoing.put_nowait((kind, payload))
        except queue.Full:
            self._ready.clear()
            self._reset.set()
            self.state.update(live_transcription_last_error="audio_queue_full")

    def _clear_queue(self) -> None:
        while True:
            try:
                self._outgoing.get_nowait()
            except queue.Empty:
                return

    def _session_update(self) -> dict[str, object]:
        transcription: dict[str, object] = {
            "model": self.config.live_transcription_model,
            "delay": self.config.live_transcription_delay,
        }
        if self.config.live_transcription_languages:
            transcription["languages"] = self.config.live_transcription_languages
        if self.config.live_transcription_prompt:
            transcription["prompt"] = self.config.live_transcription_prompt
        return {
            "type": "session.update",
            "session": {
                "type": "transcription",
                "audio": {"input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "transcription": transcription,
                    "turn_detection": None,
                }},
            },
        }

    def run(self) -> None:
        backoff = 1.0
        # Transcription sessions select their model in session.update, not the URL.
        url = "wss://api.openai.com/v1/realtime?intent=transcription"
        while not self._stop.is_set():
            ws = None
            try:
                ws = websocket.create_connection(
                    url, header=[f"Authorization: Bearer {self.config.openai_api_key}"],
                    timeout=12,
                )
                self._ws = ws
                ws.settimeout(0.05)
                ws.send(json.dumps(self._session_update(), separators=(",", ":")))
                started = time.monotonic()
                while not self._stop.is_set() and not self._reset.is_set():
                    if time.monotonic() - started > 3300:
                        break
                    if self._ready.is_set():
                        for _ in range(12):
                            try:
                                kind, payload = self._outgoing.get_nowait()
                            except queue.Empty:
                                break
                            event = (
                                {"type": "input_audio_buffer.append", "audio": base64.b64encode(payload).decode("ascii")}
                                if kind == "audio" else {"type": "input_audio_buffer.commit"}
                            )
                            ws.send(json.dumps(event, separators=(",", ":")))
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not raw:
                        raise ConnectionError("live transcription connection closed")
                    event = json.loads(raw)
                    kind = event.get("type")
                    if kind == "session.updated":
                        self._ready.set()
                        self.state.update(
                            live_transcription_connected=True,
                            live_transcription_configured=True,
                            live_transcription_last_error="",
                        )
                        LOG.info("independent live transcription configured (%s)", self.config.live_transcription_model)
                        backoff = 1.0
                    elif kind == "conversation.item.input_audio_transcription.completed":
                        transcript = event.get("transcript")
                        item_id = event.get("item_id")
                        if isinstance(transcript, str) and transcript.strip():
                            self.store.append(item_id if isinstance(item_id, str) else "", transcript,
                                session_started_at=self.session_started_at, user_id=self.user_id)
                            LOG.info("live user transcript: %s", transcript)
                    elif kind == "error":
                        error = event.get("error", {})
                        code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
                        self.state.update(live_transcription_last_error=str(code)[:120])
                        LOG.warning("live transcription server error: %s", code)
                        raise RuntimeError("live transcription server error")
            except Exception as exc:
                if not self._stop.is_set():
                    if not self.state.snapshot()["live_transcription_last_error"]:
                        self.state.update(live_transcription_last_error=type(exc).__name__)
                    LOG.warning("live transcription disconnected: %s", type(exc).__name__)
            finally:
                self._ready.clear()
                self._reset.clear()
                self._clear_queue()
                self._ws = None
                self.state.update(live_transcription_connected=False, live_transcription_configured=False)
                if ws is not None:
                    ws.close()
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, 20)
