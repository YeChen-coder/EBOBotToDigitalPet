"""Original EBO local voice confirmation and acoustic echo rejection."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import re
import numpy as np
import webrtcvad

@dataclass(frozen=True)
class BargeInDecision:
    triggered: bool
    preroll: bytes
    speech_ms: int
    echo_correlation: float
    residual_ratio: float



class BargeInGate:
    """Confirm human speech during playback while rejecting the robot's own echo."""

    FRAME_MS = 20
    INPUT_RATE = 24000
    VAD_RATE = 8000

    def __init__(
        self,
        confirm_ms: int = 300,
        preroll_ms: int = 500,
        vad_mode: int = 2,
        echo_correlation: float = 0.65,
        residual_ratio: float = 0.45,
        vad: object | None = None,
    ) -> None:
        self.confirm_ms = confirm_ms
        self.preroll_ms = preroll_ms
        self.echo_correlation = echo_correlation
        self.residual_ratio = residual_ratio
        self.vad = vad or webrtcvad.Vad(vad_mode)
        self._frame_bytes = self.INPUT_RATE * self.FRAME_MS // 1000 * 2
        self._confirm_frames = confirm_ms // self.FRAME_MS
        self._required_speech_frames = min(200, confirm_ms) // self.FRAME_MS
        self._preroll_bytes = self.INPUT_RATE * preroll_ms // 1000 * 2
        self._pending = bytearray()
        self._preroll = bytearray()
        self._frames: deque[tuple[np.ndarray, bool]] = deque(
            maxlen=self._confirm_frames
        )
        self._triggered = False

    def reset(self) -> None:
        self._pending.clear()
        self._preroll.clear()
        self._frames.clear()
        self._triggered = False

    @staticmethod
    def _downsample_24k_to_8k(pcm: bytes) -> np.ndarray:
        samples = np.frombuffer(pcm, dtype="<i2")
        return samples[::3].copy()

    def _echo_metrics(
        self,
        microphone: np.ndarray,
        reference_pcm24: bytes,
        played_ms: int,
    ) -> tuple[float, float]:
        mic = microphone.astype(np.float32)
        mic -= float(np.mean(mic))
        mic_norm = float(np.linalg.norm(mic))
        if mic_norm < 1:
            return 1.0, 0.0
        if not reference_pcm24 or played_ms <= 0:
            return 0.0, self._residual_speech_fraction(mic, mic)
        reference = np.frombuffer(reference_pcm24, dtype="<i2")[::3].astype(np.float32)
        played_end = min(reference.size, max(0, played_ms * 8))
        best_corr = 0.0
        best_residual = mic
        max_lag = min(4000, played_end)  # search up to 500 ms acoustic delay
        for lag in range(0, max_lag + 1, 80):  # 10 ms steps at 8 kHz
            end = played_end - lag
            raw_start = end - mic.size
            mic_start = max(0, -raw_start)
            start = max(0, raw_start)
            overlap = end - start
            if overlap < self._required_speech_frames * 160 or end > reference.size:
                continue
            candidate = reference[start:end].copy()
            mic_candidate = mic[mic_start : mic_start + overlap]
            candidate -= float(np.mean(candidate))
            mic_candidate = mic_candidate - float(np.mean(mic_candidate))
            ref_energy = float(np.dot(candidate, candidate))
            if ref_energy < 1:
                continue
            candidate_mic_norm = float(np.linalg.norm(mic_candidate))
            if candidate_mic_norm < 1:
                continue
            corr = abs(float(np.dot(mic_candidate, candidate))) / (
                candidate_mic_norm * (ref_energy ** 0.5) + 1e-9
            )
            scale = float(np.dot(mic_candidate, candidate)) / ref_energy
            residual = mic.copy()
            residual[mic_start : mic_start + overlap] = mic_candidate - scale * candidate
            if corr > best_corr:
                best_corr = corr
                best_residual = residual
        return best_corr, self._residual_speech_fraction(best_residual, mic)

    def _residual_speech_fraction(
        self, residual: np.ndarray, microphone: np.ndarray
    ) -> float:
        frame_samples = self.VAD_RATE * self.FRAME_MS // 1000
        total = residual.size // frame_samples
        if total <= 0:
            return 0.0
        mic_rms = float(np.sqrt(np.mean(np.square(microphone, dtype=np.float64))))
        energy_floor = max(200.0, mic_rms * 0.15)
        speech_frames = 0
        for offset in range(0, total * frame_samples, frame_samples):
            frame = residual[offset : offset + frame_samples]
            rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
            if rms < energy_floor:
                continue
            encoded = np.clip(frame, -32768, 32767).astype("<i2").tobytes()
            try:
                speech_frames += bool(self.vad.is_speech(encoded, self.VAD_RATE))
            except Exception:  # noqa: BLE001
                pass
        return speech_frames / total

    def observe(
        self,
        pcm24: bytes,
        reference_pcm24: bytes,
        played_ms: int,
    ) -> BargeInDecision:
        if not pcm24:
            return BargeInDecision(False, b"", 0, 0.0, 0.0)
        self._preroll.extend(pcm24)
        if len(self._preroll) > self._preroll_bytes:
            del self._preroll[: len(self._preroll) - self._preroll_bytes]
        self._pending.extend(pcm24)
        while len(self._pending) >= self._frame_bytes:
            frame24 = bytes(self._pending[: self._frame_bytes])
            del self._pending[: self._frame_bytes]
            frame8 = self._downsample_24k_to_8k(frame24)
            try:
                speech = bool(self.vad.is_speech(frame8.tobytes(), self.VAD_RATE))
            except Exception:  # noqa: BLE001 - malformed capture should never trigger
                speech = False
            self._frames.append((frame8, speech))
        speech_ms = sum(speech for _frame, speech in self._frames) * self.FRAME_MS
        if self._triggered or len(self._frames) < self._confirm_frames:
            return BargeInDecision(False, b"", speech_ms, 0.0, 0.0)
        microphone = np.concatenate([frame for frame, _speech in self._frames])
        correlation, residual = self._echo_metrics(
            microphone, reference_pcm24, played_ms
        )
        enough_speech = speech_ms >= self._required_speech_frames * self.FRAME_MS
        independent = (
            correlation < self.echo_correlation or residual >= self.residual_ratio
        )
        if enough_speech and independent:
            self._triggered = True
            return BargeInDecision(
                True,
                bytes(self._preroll),
                speech_ms,
                correlation,
                residual,
            )
        return BargeInDecision(False, b"", speech_ms, correlation, residual)



def actionable_transcript(transcript: str, languages: object = None) -> bool:
    """Retain the previous Chinese-household final-transcript response filter."""
    normalized = " ".join(transcript.split())
    if not normalized:
        return False
    if re.search(r"[㐀-䶿一-鿿]", normalized) or any(c.isdigit() for c in normalized):
        return True
    codes = {str(x.get('code', '')).lower() for x in languages if isinstance(x, dict)} if isinstance(languages, list) else set()
    if any(code.startswith('zh') for code in codes):
        return True
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", normalized)
    return not (words and len(words) <= 3 and len(normalized) <= 24)
