"""Configuration for the Specter conversation flow on EBO transport."""
from __future__ import annotations
import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    if value not in {'true', 'false', '1', '0', 'yes', 'no', 'on', 'off'}:
        raise ValueError(f'{name} must be a boolean')
    return value in {'true', '1', 'yes', 'on'}


@dataclass(frozen=True)
class Profile:
    id: str
    face_name: str
    display_name: str


@dataclass(frozen=True)
class Config:
    openai_api_key: str = field(default='', repr=False)
    ebo_api_token: str = field(default='', repr=False)
    control_token: str = field(default='', repr=False)
    model: str = 'gpt-realtime-2.1-mini'
    voice: str = 'marin'
    output_speed: float = 1.0
    input_transcription_model: str = 'gpt-transcribe'
    input_transcription_delay: str = ''
    input_transcription_keywords: tuple[str, ...] = ()
    input_transcription_language: str = ''
    input_transcription_languages: tuple[str, ...] = ()
    input_transcription_prompt: str = ''
    live_transcription_enabled: bool = True
    live_transcription_model: str = 'gpt-live-transcribe'
    live_transcription_delay: str = 'low'
    live_transcription_languages: tuple[str, ...] = ('zh',)
    live_transcription_prompt: str = ''
    live_transcript_path: str = '/data/live_transcripts.jsonl'
    research_model: str = 'gpt-5.4-mini'
    research_timeout_seconds: float = 90
    trace_enabled: bool = False
    instructions: str = '你是家里的 EBO 机器人助手。用自然、简洁、温暖的中文交谈。没有把握就明确说不知道。'
    rtsp_url: str = 'rtsp://ebo-engine:8554/ebo'
    ebo_api_url: str = 'http://ebo-engine:8098'
    ebo_node: str = 'ebo'
    talk_stream_url: str = 'ws://ebo-engine:8200/talk'
    audio_stream_url: str = ''  # Empty derives /listen from the talkback host/port.
    stream_prebuffer_ms: int = 200
    stream_connect_timeout_seconds: float = 10
    public_audio_base_url: str = 'http://realtime-assistant:8099/audio'
    http_port: int = 8099
    auto_wake: bool = True
    frigate_url: str = 'http://frigate:5000'
    camera_name: str = 'ebo'
    mqtt_host: str = 'mosquitto'
    mqtt_port: int = 1883
    image_width: int = 768
    image_quality: int = 75
    visual_enabled: bool = True
    proactive_greeting: bool = False
    voice_wake_enabled: bool = True
    playback_tail_ms: int = 800
    min_face_score: float = .90
    min_person_area: int = 40000
    absence_seconds: float = 25
    cooldown_seconds: float = 90
    session_idle_seconds: float = 300
    session_max_seconds: float = 2700
    input_noise_reduction: str = 'far_field'
    vad_threshold: float = .65
    vad_prefix_padding_ms: int = 300
    vad_silence_duration_ms: int = 650
    barge_in_enabled: bool = False
    barge_in_confirm_ms: int = 300
    barge_in_preroll_ms: int = 500
    barge_in_vad_mode: int = 2
    barge_in_echo_correlation: float = .65
    barge_in_residual_ratio: float = .45
    aec_enabled: bool = True
    aec_delay_ms: int = 0
    aec_warmup_ms: int = 500
    media_stale_after_seconds: float = 20
    media_startup_grace_seconds: float = 90
    transcript_path: str = '/data/transcripts.jsonl'
    output_audio_dir: str = '/data/replies'
    assistant_transcript_path: str = '/data/assistant_outputs.jsonl'
    memory_root: str = '/data/memory-v2'
    assistant_control_path: str = ''
    memory_max_chars: int = 6000
    profiles: tuple[Profile, ...] = (Profile('father', '爸爸', '爸爸'), Profile('mother', '妈妈', '妈妈'))

    @classmethod
    def from_env(cls) -> Config:
        # Restore audio gates only; legacy motion/image append settings stay retired.
        names = {
            'assistant_control_path': 'EBO_ASSISTANT_CONTROL_PATH',
            'model': 'OPENAI_REALTIME_MODEL', 'voice': 'OPENAI_REALTIME_VOICE',
            'output_speed': 'OPENAI_REALTIME_OUTPUT_SPEED', 'input_transcription_model': 'OPENAI_INPUT_TRANSCRIPTION_MODEL',
            'input_transcription_delay': 'OPENAI_INPUT_TRANSCRIPTION_DELAY',
            'input_transcription_language': 'OPENAI_INPUT_TRANSCRIPTION_LANGUAGE',
            'input_transcription_prompt': 'OPENAI_INPUT_TRANSCRIPTION_PROMPT',
            'live_transcription_enabled': 'OPENAI_LIVE_TRANSCRIPTION_ENABLED',
            'live_transcription_model': 'OPENAI_LIVE_TRANSCRIPTION_MODEL',
            'live_transcription_delay': 'OPENAI_LIVE_TRANSCRIPTION_DELAY',
            'live_transcription_prompt': 'OPENAI_LIVE_TRANSCRIPTION_PROMPT',
            'live_transcript_path': 'EBO_LIVE_TRANSCRIPT_PATH',
            'research_model': 'OPENAI_RESEARCH_MODEL', 'research_timeout_seconds': 'OPENAI_RESEARCH_TIMEOUT_SECONDS',
            'instructions': 'EBO_ASSISTANT_INSTRUCTIONS', 'rtsp_url': 'EBO_RTSP_URL',
            'ebo_api_url': 'EBO_API_URL', 'ebo_node': 'EBO_NODE', 'talk_stream_url': 'EBO_TALK_STREAM_URL',
            'audio_stream_url': 'EBO_AUDIO_STREAM_URL',
            'stream_prebuffer_ms': 'EBO_STREAM_PREBUFFER_MS', 'stream_connect_timeout_seconds': 'EBO_STREAM_CONNECT_TIMEOUT_SECONDS',
            'public_audio_base_url': 'EBO_ASSISTANT_AUDIO_URL', 'http_port': 'EBO_ASSISTANT_PORT',
            'auto_wake': 'EBO_AUTO_WAKE', 'frigate_url': 'EBO_FRIGATE_URL', 'camera_name': 'EBO_CAMERA_NAME',
            'mqtt_host': 'EBO_MQTT_HOST', 'mqtt_port': 'EBO_MQTT_PORT', 'image_width': 'REALTIME_IMAGE_WIDTH',
            'image_quality': 'REALTIME_IMAGE_QUALITY', 'visual_enabled': 'EBO_VISUAL_ENABLED',
            'proactive_greeting': 'EBO_PROACTIVE_GREETING_ENABLED', 'min_face_score': 'EBO_MIN_FACE_SCORE',
            'voice_wake_enabled': 'EBO_VOICE_WAKE_ENABLED', 'playback_tail_ms': 'EBO_PLAYBACK_TAIL_MS',
            'min_person_area': 'EBO_MIN_PERSON_AREA', 'absence_seconds': 'EBO_ABSENCE_SECONDS',
            'cooldown_seconds': 'EBO_COOLDOWN_SECONDS', 'session_idle_seconds': 'EBO_SESSION_IDLE_SECONDS',
            'session_max_seconds': 'EBO_SESSION_MAX_SECONDS', 'input_noise_reduction': 'EBO_SERVER_NOISE_REDUCTION',
            'vad_threshold': 'REALTIME_VAD_THRESHOLD', 'vad_prefix_padding_ms': 'EBO_VAD_PREFIX_PADDING_MS',
            'vad_silence_duration_ms': 'EBO_VAD_SILENCE_DURATION_MS', 'barge_in_enabled': 'EBO_BARGE_IN_ENABLED',
            'barge_in_confirm_ms': 'EBO_BARGE_IN_CONFIRM_MS', 'barge_in_preroll_ms': 'EBO_BARGE_IN_PREROLL_MS',
            'barge_in_vad_mode': 'EBO_BARGE_IN_VAD_MODE', 'barge_in_echo_correlation': 'EBO_BARGE_IN_ECHO_CORRELATION',
            'barge_in_residual_ratio': 'EBO_BARGE_IN_RESIDUAL_RATIO',
            'aec_enabled': 'EBO_AEC_ENABLED', 'aec_delay_ms': 'EBO_AEC_DELAY_MS', 'aec_warmup_ms': 'EBO_AEC_WARMUP_MS',
            'media_stale_after_seconds': 'EBO_MEDIA_STALE_AFTER_SECONDS', 'media_startup_grace_seconds': 'EBO_MEDIA_STARTUP_GRACE_SECONDS',
            'transcript_path': 'EBO_TRANSCRIPT_PATH', 'output_audio_dir': 'EBO_OUTPUT_AUDIO_DIR',
            'assistant_transcript_path': 'EBO_ASSISTANT_TRANSCRIPT_PATH', 'memory_root': 'EBO_MEMORY_ROOT',
            'memory_max_chars': 'EBO_REALTIME_MEMORY_MAX_CHARS', 'trace_enabled': 'EBO_TRACE_ENABLED',
        }
        defaults = cls()
        values = {}
        for attribute, name in names.items():
            default = getattr(defaults, attribute)
            if isinstance(default, bool):
                values[attribute] = env_bool(name, default)
            else:
                raw = os.getenv(name)
                values[attribute] = type(default)(raw.strip()) if raw and raw.strip() else default
        values['voice'] = values['voice'].lower()
        for attr, name in [('input_transcription_keywords', 'OPENAI_INPUT_TRANSCRIPTION_KEYWORDS_JSON'),
                           ('input_transcription_languages', 'OPENAI_INPUT_TRANSCRIPTION_LANGUAGES_JSON'),
                           ('live_transcription_languages', 'OPENAI_LIVE_TRANSCRIPTION_LANGUAGES_JSON')]:
            raw = os.getenv(name)
            items = json.loads(raw) if raw and raw.strip() else list(getattr(defaults, attr))
            if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
                raise ValueError(f'{name} must be a JSON string array')
            values[attr] = tuple(items)
        for attr, name in [('openai_api_key', 'OPENAI_API_KEY'), ('ebo_api_token', 'EBO_API_TOKEN')]:
            values[attr] = os.getenv(name, '').strip()
        values['control_token'] = os.getenv('EBO_ASSISTANT_CONTROL_TOKEN', '').strip() or values['ebo_api_token']
        raw_profiles = os.getenv('EBO_USERS_JSON')
        if raw_profiles:
            profiles = json.loads(raw_profiles)
            if not isinstance(profiles, list):
                raise ValueError('EBO_USERS_JSON must be an array')
            values['profiles'] = tuple(Profile(**profile) for profile in profiles)
        result = cls(**values)
        result.validate()
        return result

    def validate(self) -> None:
        if not self.openai_api_key or not self.ebo_api_token or not self.control_token:
            raise ValueError('OPENAI_API_KEY and EBO_API_TOKEN are required')
        if self.input_transcription_delay not in {'', 'minimal', 'low', 'medium', 'high', 'xhigh'}:
            raise ValueError('Invalid input transcription delay')
        if self.live_transcription_delay not in {'minimal', 'low', 'medium', 'high', 'xhigh'}:
            raise ValueError('Invalid live transcription delay')
        if not self.input_transcription_model or (self.live_transcription_enabled and not self.live_transcription_model):
            raise ValueError('Transcription model is required')
        if self.live_transcription_enabled and not self.live_transcript_path:
            raise ValueError('Live transcript path is required')
        if not 200 <= self.barge_in_confirm_ms <= 2000 or self.barge_in_confirm_ms % 20:
            raise ValueError('Barge-in confirmation must be 200..2000 ms in 20 ms steps')
        if not self.barge_in_confirm_ms <= self.barge_in_preroll_ms <= 5000:
            raise ValueError('Barge-in preroll must cover confirmation and be at most 5000 ms')
        if self.barge_in_vad_mode not in {0, 1, 2, 3} or not all(0 <= x <= 1 for x in (self.barge_in_echo_correlation, self.barge_in_residual_ratio)):
            raise ValueError('Invalid local speech gate configuration')
        if not self.profiles or len(self.profiles) > 10:
            raise ValueError('Configure between one and ten EBO users')
        for profile in self.profiles:
            if not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', profile.id) or not profile.face_name.strip() or not profile.display_name.strip():
                raise ValueError('Profiles require a safe ASCII id, face_name and display_name')
        if len({p.id for p in self.profiles}) != len(self.profiles) or len({p.face_name for p in self.profiles}) != len(self.profiles):
            raise ValueError('User IDs and face names must be unique')
        for attribute in ('research_timeout_seconds', 'stream_connect_timeout_seconds', 'absence_seconds', 'cooldown_seconds', 'session_idle_seconds', 'session_max_seconds', 'media_stale_after_seconds', 'media_startup_grace_seconds'):
            value = getattr(self, attribute)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{attribute} must be finite and positive')
        if not 30 <= self.session_max_seconds <= 3300 or self.session_idle_seconds > self.session_max_seconds:
            raise ValueError('Session limit must be 30..3300 seconds and idle must not exceed it')
        if not 0 < self.min_face_score <= 1 or not 0 < self.vad_threshold < 1:
            raise ValueError('Face and VAD thresholds are out of range')
        if self.input_noise_reduction not in {'far_field', 'near_field', 'off'}:
            raise ValueError('EBO_SERVER_NOISE_REDUCTION must be far_field, near_field or off')
        if not 0 <= self.vad_prefix_padding_ms <= 5000 or not 100 <= self.vad_silence_duration_ms <= 5000:
            raise ValueError('VAD timing is out of range')
        if not 0 <= self.aec_delay_ms <= 500 or not 0 <= self.aec_warmup_ms <= 5000:
            raise ValueError('AEC timing is out of range')
        if not 200 <= self.playback_tail_ms <= 5000:
            raise ValueError('Playback tail must be 200..5000 ms')
        if not 0 <= self.stream_prebuffer_ms <= 2000 or not 0.25 <= self.output_speed <= 1.5:
            raise ValueError('Playback parameters are out of range')
        if not 256 <= self.image_width <= 1920 or not 30 <= self.image_quality <= 95 or self.memory_max_chars < 100:
            raise ValueError('Image or memory limits are out of range')
        if self.min_person_area <= 0 or not 1 <= self.mqtt_port <= 65535 or not 1 <= self.http_port <= 65535:
            raise ValueError('Person area or ports are out of range')
        if not Path(self.memory_root).is_absolute():
            raise ValueError('EBO_MEMORY_ROOT must be absolute')

    def profile(self, user_id: str) -> Profile:
        for profile in self.profiles:
            if profile.id == user_id:
                return profile
        raise ValueError('unknown_user')

    def memory_paths(self, user_id: str) -> tuple[Path, Path]:
        self.profile(user_id)
        directory = Path(self.memory_root) / user_id
        return directory / 'sessions.json', directory / 'long_term.json'

    def session_settings(self) -> dict:
        pcm = {'type': 'audio/pcm', 'rate': 24000}
        transcription = {'model': self.input_transcription_model}
        for key, value in [('delay', self.input_transcription_delay), ('keywords', self.input_transcription_keywords),
                           ('language', self.input_transcription_language), ('languages', self.input_transcription_languages),
                           ('prompt', self.input_transcription_prompt)]:
            if value:
                transcription[key] = list(value) if isinstance(value, tuple) else value
        return {
            'model_name': self.model, 'output_modalities': ['audio'],
            'audio': {'input': {
                'format': pcm, 'transcription': transcription,
                'noise_reduction': None if self.input_noise_reduction == 'off' else {'type': self.input_noise_reduction},
                'turn_detection': {'type': 'server_vad', 'threshold': self.vad_threshold,
                    'prefix_padding_ms': self.vad_prefix_padding_ms, 'silence_duration_ms': self.vad_silence_duration_ms,
                    'create_response': False, 'interrupt_response': False},
            }, 'output': {'format': pcm, 'voice': self.voice, 'speed': self.output_speed}},
        }
