"""Fetch a fresh Frigate camera frame without storing it on disk."""

from __future__ import annotations

import io
import json
import math
import time
from urllib.parse import quote
from urllib.request import Request, urlopen


class VisualUnavailable(RuntimeError):
    pass


class FrigateFrameSource:
    def __init__(
        self,
        base_url: str,
        camera_name: str,
        width: int = 768,
        quality: int = 75,
        timeout: float = 2.0,
        source_health=None,
    ) -> None:
        if not 256 <= width <= 1920:
            raise ValueError("image width must be between 256 and 1920")
        if not 30 <= quality <= 95:
            raise ValueError("JPEG quality must be between 30 and 95")
        self.base_url = base_url.rstrip("/")
        self.camera_name = camera_name
        self.width = width
        self.quality = quality
        self.timeout = timeout
        self.source_health = source_health

    def _read(self, path: str) -> bytes:
        request = Request(f"{self.base_url}/api/{path}", headers={"Cache-Control": "no-cache"})
        with urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def latest_frame(self):
        """Return a verified live RGB frame for callers needing full resolution.

        中文：先检查 Frigate 相机状态，再取原尺寸画面；调用方可自行裁剪目标。
        """
        from PIL import Image

        try:
            if self.source_health is not None:
                health = self.source_health()
                if health.get('engine_video_monitor_enabled') and health.get('source_video_ok') is not True:
                    raise VisualUnavailable("Robot video source is stale or unavailable")
            stats = json.loads(self._read("stats"))
            camera = stats["cameras"][self.camera_name]
            fps = float(camera["camera_fps"])
            if not math.isfinite(fps) or fps <= 0:
                raise VisualUnavailable("Frigate camera is offline")
            stamp = float(stats["service"]["last_updated"])
            if not math.isfinite(stamp) or not -5 <= time.time() - stamp <= 30:
                raise VisualUnavailable("Frigate camera stats are stale")
            raw = self._read(f"{quote(self.camera_name, safe='')}/latest.jpg")
            with Image.open(io.BytesIO(raw)) as frame:
                return frame.convert("RGB")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            if isinstance(exc, VisualUnavailable):
                raise
            raise VisualUnavailable(f"Could not get a live Frigate frame: {type(exc).__name__}") from exc

    def latest_jpeg(self) -> bytes:
        """Shrink a live frame for the existing Realtime conversation.

        中文：保持原有语音会话的图片尺寸和压缩方式不变。
        """
        from PIL import Image

        frame = self.latest_frame()
        frame.thumbnail((self.width, self.width), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        frame.save(output, format="JPEG", quality=self.quality, optimize=True)
        return output.getvalue()
