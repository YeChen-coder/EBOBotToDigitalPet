import io
import json
import time

from PIL import Image
import pytest

from visual import FrigateFrameSource, VisualUnavailable


def test_latest_frame_is_resized_in_memory():
    source = FrigateFrameSource("http://127.0.0.1:15000", "desk_camera", width=768)
    image = io.BytesIO()
    Image.new("RGB", (1280, 720), "blue").save(image, format="JPEG")
    paths = []

    def read(path):
        paths.append(path)
        if path == "stats":
            return json.dumps({
                "cameras": {"desk_camera": {"camera_fps": 5}},
                "service": {"last_updated": time.time()},
            }).encode()
        return image.getvalue()

    source._read = read
    result = source.latest_jpeg()
    with Image.open(io.BytesIO(result)) as resized:
        assert resized.size == (768, 432)
    assert paths == ["stats", "desk_camera/latest.jpg"]


def test_offline_camera_does_not_send_cached_preview():
    source = FrigateFrameSource("http://127.0.0.1:15000", "desk_camera")
    source._read = lambda _path: json.dumps({
        "cameras": {"desk_camera": {"camera_fps": 0}},
        "service": {"last_updated": time.time()},
    }).encode()
    with pytest.raises(VisualUnavailable, match="offline"):
        source.latest_jpeg()


def test_held_rtsp_frames_never_count_as_live_robot_picture():
    source = FrigateFrameSource('http://frigate:5000', 'ebo', source_health=lambda: {
        'engine_video_monitor_enabled':True, 'source_video_ok':False})
    source._read = lambda _: pytest.fail('stale source must be rejected before fetching cached JPEG')
    with pytest.raises(VisualUnavailable, match='source is stale'):
        source.latest_jpeg()
