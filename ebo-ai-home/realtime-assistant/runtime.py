"""EBO media -> Frigate identity gate -> Specter voice framework -> EBO audio."""
from __future__ import annotations
import asyncio
import hmac
import json
import logging
import math
import signal
import threading
import time
from urllib.parse import urlsplit, urlunsplit
import websocket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import paho.mqtt.client as mqtt
from config import Config, Profile
from conversation import Conversation
from ebo_transport import AudioStore, AssistantOutputStore, EboAPI, Speaker, TranscriptStore
from presence import PresenceGate
from session_memory import consolidation_due, consolidate_memory
from state import RuntimeState
from visual import FrigateFrameSource
from standby_voice import StandbyVoice
from session_control import AssistantPreference

LOG = logging.getLogger('ebo-assistant')


class Supervisor:
    def __init__(self, config, state, speaker, transcripts, outputs):
        self.config, self.state, self.speaker = config, state, speaker
        self.transcripts, self.outputs = transcripts, outputs
        self.lock = threading.RLock()
        self.active = None
        self.worker = None
        self.stopping = threading.Event()
        preference_path = config.assistant_control_path or str(Path(config.memory_root).parent/'assistant-control.json')
        self.preference = AssistantPreference(preference_path)
        self.enabled = self.preference.load()
        self.memory_task = self.memory_event_loop = None
        state.update(assistant_enabled=self.enabled, assistant_control_error=self.preference.error)
        if not self.enabled:
            speaker.suspend()
        self.frame_source = FrigateFrameSource(config.frigate_url, config.camera_name, config.image_width, config.image_quality,
                                               source_health=state.snapshot)
        self.gates = {p.id: PresenceGate(p.face_name, config.camera_name, config.min_face_score,
            config.min_person_area, config.absence_seconds, config.cooldown_seconds) for p in config.profiles}
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='ebo-specter-listener')
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.wake = StandbyVoice(config, state, self.voice_eligible, self.accept_voice)

    def voice_eligible(self):
        snapshot = self.state.snapshot()
        return (self.enabled and not self.stopping.is_set() and self.active is None
                and snapshot['listener_ready'] and snapshot['source_audio_ok']
                and snapshot['audio_streaming'] and not self.speaker.input_muted())

    def accept_voice(self, turn):
        with self.lock:
            if not self.voice_eligible():
                return False
            # Face presence is only an identity hint. Unknown/multiple/stale
            # people use an ephemeral guest session without parental memories.
            now = time.monotonic()
            tracks = {}
            for gate in self.gates.values():
                for object_id, track in gate.tracks.items():
                    if now-track.last_seen <= self.config.absence_seconds:
                        tracks[object_id] = track
            user_id = 'guest'
            snapshot = self.state.snapshot()
            if snapshot['mqtt_connected'] and snapshot['video_streaming'] and len(tracks) == 1:
                track = next(iter(tracks.values()))
                for profile in self.config.profiles:
                    if (track.name == profile.face_name and track.score >= self.config.min_face_score
                            and track.area >= self.config.min_person_area):
                        user_id = profile.id
            return self.start(user_id, 'voice', turn)

    def start(self, user_id, trigger='manual', initial_turn=None):
        profile = (Profile('guest', '', '家人') if user_id == 'guest' and trigger == 'voice'
                   else self.config.profile(user_id))
        with self.lock:
            if not self.enabled:
                raise ValueError('assistant_paused')
            if self.stopping.is_set() or self.active is not None:
                return False
            snapshot = self.state.snapshot()
            ready = self.voice_eligible() if trigger == 'voice' else (
                snapshot['listener_ready'] and snapshot['audio_ready'])
            if trigger == 'face':
                ready = ready and snapshot['video_streaming'] and snapshot['mqtt_connected']
            if not ready:
                raise ValueError('media_not_ready')
            conversation = Conversation(self.config, profile, self.frame_source if self.config.visual_enabled else None,
                self.speaker, self.state, self.transcripts, self.outputs, trigger)
            if initial_turn is not None:
                conversation.initial_turn = initial_turn
            self.active = conversation
            self.wake.reset()
            self.state.update(session_state='connecting', active_user=user_id)
            def run():
                try:
                    asyncio.run(conversation.run())
                except Exception as exc:
                    self.state.update(last_error=f'session_failed:{type(exc).__name__}')
                    LOG.warning('Voice session failed: %s', type(exc).__name__)
                finally:
                    self.state.increment('sessions_completed')
                    with self.lock:
                        self.active = None
                        self.state.update(session_state='standby', active_user=None, session_id=None, realtime_connected=False)
            self.worker = threading.Thread(target=run, name='ebo-conversation', daemon=True)
            self.worker.start()
            return True

    def close(self):
        with self.lock:
            if self.active:
                self.active.request_close()
                return True
            return False

    def set_enabled(self, enabled):
        with self.lock:
            self.preference.save(enabled)
            self.enabled = enabled
            self.state.update(assistant_enabled=enabled, assistant_control_error='')
            self.wake.reset()
            if enabled:
                self.speaker.resume()
            else:
                if self.active:
                    self.active.request_abort()
                if self.memory_task and self.memory_event_loop:
                    self.memory_event_loop.call_soon_threadsafe(self.memory_task.cancel)
                self.speaker.suspend()
            return True

    def offer_audio(self, pcm):
        with self.lock:
            if not self.enabled:
                return
            self.state.update(speech_input_blocked=not self.config.barge_in_enabled and bool(
                self.speaker.input_muted() or (self.active and self.active.response_active)))
            if self.active:
                self.active.offer_audio(pcm)
            else:
                self.wake.offer_audio(pcm)

    def on_connect(self, client, _userdata, _flags, reason, _properties):
        connected = not reason.is_failure
        self.state.update(mqtt_connected=connected)
        if connected:
            client.subscribe([('frigate/events', 0), ('frigate/tracked_object_update', 0)])
            with self.lock:
                for gate in self.gates.values():
                    gate.tracks.clear()

    def on_disconnect(self, _client, _userdata, _flags, _reason, _properties):
        self.state.update(mqtt_connected=False)

    def on_message(self, _client, _userdata, message):
        if message.retain:
            return
        try:
            payload = json.loads(message.payload)
            if not isinstance(payload, dict):
                return
            with self.lock:
                for user_id, gate in self.gates.items():
                    previous = gate.last_greeting, gate.greeted_encounter
                    if gate.observe(message.topic, payload):
                        if not self.enabled or self.active or not self.config.proactive_greeting:
                            gate.last_greeting, gate.greeted_encounter = previous
                        else:
                            try:
                                if not self.start(user_id, 'face'):
                                    gate.last_greeting, gate.greeted_encounter = previous
                            except ValueError:
                                gate.last_greeting, gate.greeted_encounter = previous
        except (ValueError, TypeError, KeyError):
            LOG.warning('Ignored malformed Frigate event')

    def consider_present_users(self):
        with self.lock:
            if not self.enabled or self.active or not self.config.proactive_greeting or not self.state.snapshot()['mqtt_connected']:
                return
            now = time.monotonic()
            for user_id, gate in self.gates.items():
                gate._expire(now)
                for track in gate.tracks.values():
                    previous = gate.last_greeting, gate.greeted_encounter
                    if gate._should_greet(track, now):
                        try:
                            if self.start(user_id, 'face'):
                                return
                        except ValueError:
                            pass
                        gate.last_greeting, gate.greeted_encounter = previous

    def monitor_frigate(self):
        next_faces = 0
        face_counts = {}
        while not self.stopping.is_set():
            try:
                stats = json.loads(self.frame_source._read('stats'))
                camera = stats['cameras'][self.config.camera_name]
                stamp = float(stats['service']['last_updated'])
                fps = float(camera['camera_fps'])
                live = math.isfinite(stamp) and -5 <= time.time()-stamp < 30 and math.isfinite(fps) and fps > 0
                self.state.update(frigate_ready=live)
                if live:
                    self.state.mark_media('frame')
            except (OSError, ValueError, KeyError, TypeError):
                self.state.update(frigate_ready=False)
            if time.monotonic() >= next_faces:
                try:
                    faces = json.loads(self.frame_source._read('faces'))
                    if not isinstance(faces, dict):
                        raise ValueError('invalid_face_library')
                    face_counts = {p.id: len(faces.get(p.face_name, [])) for p in self.config.profiles}
                    self.state.update(face_library_ready=True, face_library_checked_at=time.time())
                except (OSError, ValueError, TypeError):
                    self.state.update(face_library_ready=False)
                next_faces = time.monotonic() + 30
                self.state.update(profiles=[{'id': p.id, 'name': p.display_name, 'face_name': p.face_name,
                    'enrolled_images': face_counts.get(p.id, 0)} for p in self.config.profiles])
            self.consider_present_users()
            self.stopping.wait(2)

    def memory_loop(self):
        while not self.stopping.is_set():
            for profile in self.config.profiles:
                if not self.enabled:
                    break
                sessions, long_term = self.config.memory_paths(profile.id)
                try:
                    if consolidation_due(sessions, long_term):
                        self.state.update(memory_pending=True, memory_status='consolidating')
                        async def consolidate():
                            with self.lock:
                                if not self.enabled:
                                    return False
                                self.memory_event_loop = asyncio.get_running_loop()
                                self.memory_task = asyncio.create_task(consolidate_memory(
                                    sessions, long_term, tracing_disabled=not self.config.trace_enabled))
                            try:
                                await self.memory_task
                                return True
                            except asyncio.CancelledError:
                                return False
                            finally:
                                with self.lock:
                                    self.memory_task = self.memory_event_loop = None
                        if asyncio.run(consolidate()):
                            self.state.update(memory_pending=False, memory_status='consolidated', memory_consolidation_at=time.time(), memory_last_error='')
                        else:
                            self.state.update(memory_pending=False)
                except Exception as exc:
                    self.state.update(memory_pending=False, memory_status='failed', memory_last_error=type(exc).__name__)
                    LOG.warning('Memory consolidation failed: %s', type(exc).__name__)
            self.stopping.wait(60)

    def run(self):
        self.client.connect_async(self.config.mqtt_host, self.config.mqtt_port, keepalive=30)
        self.client.loop_start()
        self.state.update(listener_ready=True, session_state='standby')
        while not self.stopping.wait(1):
            pass
        self.client.disconnect()
        self.client.loop_stop()

    def stop(self):
        self.stopping.set()
        self.wake.stop()
        with self.lock:
            if self.active and self.active.loop:
                self.active.loop.call_soon_threadsafe(self.active.stop.set)
        if self.worker:
            self.worker.join(timeout=55)


class MediaCapture:
    """EBO audio capture; Frigate owns video inspection and JPEG selection."""
    def __init__(self, config, supervisor, ebo, state):
        self.config, self.supervisor, self.ebo, self.state = config, supervisor, ebo, state
        self.stopping = threading.Event()
        self.socket = None

    def _audio_connection(self):
        parts = urlsplit(self.config.talk_stream_url)
        url = self.config.audio_stream_url or urlunsplit((parts.scheme, parts.netloc, '/listen', '', ''))
        return websocket.create_connection(url, timeout=10)

    def _receive_audio(self, connection):
        connection.send(json.dumps({'type': 'start', 'token': self.config.ebo_api_token,
            'node': self.config.ebo_node, 'rate': 24000, 'channels': 1, 'format': 'pcm16'}))
        ready = json.loads(connection.recv())
        if ready != {'type': 'ready', 'rate': 24000, 'channels': 1, 'format': 'pcm16'}:
            raise ValueError('invalid_audio_stream_handshake')
        self.state.update(audio_capture_error='', audio_capture_transport='pcm_websocket')
        pending = bytearray()
        while not self.stopping.is_set():
            chunk = connection.recv()
            if not isinstance(chunk, bytes) or not chunk or len(chunk) % 2:
                raise ValueError('invalid_audio_stream_pcm')
            pending.extend(chunk)
            while len(pending) >= 4800:
                pcm = bytes(pending[:4800])
                del pending[:4800]
                self.state.mark_media('audio')
                self.supervisor.offer_audio(pcm)

    def audio_loop(self):
        while not self.stopping.is_set():
            try:
                self.socket = self._audio_connection()
                self._receive_audio(self.socket)
            except Exception as exc:
                if not self.stopping.is_set():
                    self.state.update(audio_capture_error=type(exc).__name__)
                    LOG.warning('Independent microphone stream unavailable: %s', type(exc).__name__)
            finally:
                if self.socket:
                    self.socket.close()
                    self.socket = None
            if not self.stopping.is_set():
                self.ebo.wake_if_due()
                self.stopping.wait(3)

    def audio_health_loop(self):
        while not self.stopping.is_set():
            try:
                health = self.ebo.media_health()
                self.state.update(engine_audio_health=health['audio'], engine_audio_checked_at=time.time(), engine_audio_error='',
                                  engine_video_health=health['video'], engine_video_checked_at=time.time(), engine_video_error='')
            except Exception as exc:
                self.state.update(engine_audio_error=type(exc).__name__, engine_video_error=type(exc).__name__)
            self.stopping.wait(5)

    def stop(self):
        self.stopping.set()
        if self.socket:
            self.socket.close()


def make_http_handler(store, state, supervisor, config):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, payload):
            raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == '/health':
                return self.send_json(200, state.snapshot())
            if self.path.startswith('/audio/'):
                name = self.path.removeprefix('/audio/').split('?', 1)[0]
                if Path(name).name != name or not name.startswith('reply-') or not name.endswith('.wav'):
                    return self.send_error(404)
                path = store.directory / name
                if not path.is_file():
                    return self.send_error(404)
                raw = path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'audio/wav')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(raw)
                return
            self.send_error(404)

        def do_POST(self):
            if self.path not in {'/session/start', '/session/close', '/assistant/pause', '/assistant/resume'}:
                return self.send_error(404)
            token = self.headers.get('X-EBO-Control-Token', '')
            if not token or not hmac.compare_digest(token, config.control_token):
                return self.send_json(403, {'error': 'invalid_control_token'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024:
                    return self.send_json(413, {'error': 'invalid_body_size'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('invalid_body')
                if self.path in {'/assistant/pause', '/assistant/resume'}:
                    supervisor.set_enabled(self.path.endswith('/resume'))
                    return self.send_json(200, {'accepted': True, 'assistant_enabled': state.snapshot()['assistant_enabled']})
                if self.path == '/session/start':
                    started = supervisor.start(body.get('user_id', ''))
                    return self.send_json(202 if started else 409, {'accepted': started, 'error': None if started else 'session_busy'})
                return self.send_json(202, {'accepted': supervisor.close()})
            except (ValueError, TypeError) as exc:
                code = str(exc)
                return self.send_json(409 if code == 'assistant_paused' else 400,
                                      {'error': code if code in {'unknown_user', 'media_not_ready', 'assistant_paused'} else 'invalid_body'})
            except OSError:
                return self.send_json(503, {'error': 'assistant_preference_save_failed'})

        def log_message(self, _format, *_args):
            pass
    return Handler


def main():
    logging.basicConfig(level='INFO', format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    config = Config.from_env()
    state = RuntimeState()
    state.update(media_stale_after_seconds=config.media_stale_after_seconds,
        media_startup_grace_seconds=config.media_startup_grace_seconds,
        barge_in_enabled=config.barge_in_enabled, engine_audio_monitor_enabled=True, engine_video_monitor_enabled=True)
    state.update(interruption_control='local_echo_gate' if config.barge_in_enabled else 'half_duplex',
        playback_tail_ms=config.playback_tail_ms)
    ebo = EboAPI(config, state)
    store = AudioStore(Path(config.output_audio_dir), state)
    transcripts = TranscriptStore(Path(config.transcript_path), state, source='gate')
    outputs = AssistantOutputStore(Path(config.assistant_transcript_path), store, state)
    speaker = Speaker(config, ebo, store, state)
    supervisor = Supervisor(config, state, speaker, transcripts, outputs)
    capture = MediaCapture(config, supervisor, ebo, state)
    httpd = ThreadingHTTPServer(('0.0.0.0', config.http_port), make_http_handler(store, state, supervisor, config))
    threads = [threading.Thread(target=fn, daemon=True, name=name) for name, fn in [
        ('listener', supervisor.run), ('frigate-monitor', supervisor.monitor_frigate),
        ('memory', supervisor.memory_loop), ('audio', capture.audio_loop),
        ('audio-health', capture.audio_health_loop), ('http', httpd.serve_forever)]]
    if config.voice_wake_enabled:
        threads.append(threading.Thread(target=supervisor.wake.run, daemon=True, name='standby-voice'))
    stop = threading.Event()
    def shutdown(_signum, _frame):
        stop.set()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    for thread in threads:
        thread.start()
    LOG.info('Specter EBO framework ready: Frigate images, server VAD, isolated family memory')
    while not stop.wait(1):
        if any(not t.is_alive() for t in threads):
            LOG.error('A service worker stopped unexpectedly')
            break
    capture.stop()
    supervisor.stop()
    httpd.shutdown()
    httpd.server_close()


if __name__ == '__main__':
    main()
