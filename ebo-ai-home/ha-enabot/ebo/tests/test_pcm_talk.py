import json
import threading
from unittest.mock import Mock
import pytest
from websockets.sync.server import serve
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed

from pcm_talk import FRAME_BYTES, PcmStream, PcmTalkServer


def test_24khz_pcm_is_resampled_into_8khz_20ms_frames():
    stream = PcmStream("stream-test")
    stream.push(b"\x01\x00" * 960)  # 40 ms at 24 kHz
    stream.finish_input()

    first = stream.pop_frame()
    second = stream.pop_frame()
    assert first is not None and len(first) == FRAME_BYTES
    assert second is not None and len(second) == FRAME_BYTES
    assert stream.pop_frame() is None
    assert stream.drained()


def test_played_ms_counts_only_frames_actually_sent():
    stream = PcmStream("stream-test")
    assert stream.played_ms == 0
    stream.mark_played()
    stream.mark_played()
    assert stream.played_ms == 40


def test_stream_authentication_requires_token_format_rate_and_node():
    server = PcmTalkServer("127.0.0.1", 0, "secret", "ebo", lambda _s: None, lambda _s: None)
    valid = json.dumps(
        {
            "type": "start",
            "token": "secret",
            "node": "ebo",
            "stream_id": "one",
            "rate": 24000,
            "channels": 1,
            "format": "pcm16",
        }
    )
    assert server._authenticate(valid)[0]
    assert not server._authenticate(valid.replace("secret", "wrong"))[0]
    assert not server._authenticate(valid.replace("24000", "16000"))[0]
    assert not server._authenticate(valid.replace('"ebo"', '"other"'))[0]


def test_replacing_a_stream_marks_the_old_one_stopped():
    old = PcmStream("old")
    old.push(b"\0\0" * 480)
    old.stop("replaced")
    assert old.stopped.is_set()
    assert old.stop_reason == "replaced"
    assert old.pop_frame() is None


def test_real_listen_socket_authenticates_and_streams_without_video_or_talk():
    activate = Mock()
    server = PcmTalkServer('127.0.0.1', 0, 'secret', 'ebo', activate, Mock())
    hello = {'type':'start','token':'secret','node':'ebo','rate':24000,'channels':1,'format':'pcm16'}
    with serve(server._handle, '127.0.0.1', 0) as endpoint:
        worker = threading.Thread(target=endpoint.serve_forever, daemon=True)
        worker.start()
        url = f'ws://127.0.0.1:{endpoint.socket.getsockname()[1]}/listen'
        try:
            with connect(url) as bad:
                bad.send(json.dumps({**hello, 'token':'wrong'}))
                with pytest.raises(ConnectionClosed):
                    bad.recv(timeout=1)
            with connect(url) as first, connect(url) as second:
                for client in (first, second):
                    client.send(json.dumps(hello))
                    assert json.loads(client.recv(timeout=1))['rate'] == 24000
                    with pytest.raises(TimeoutError):
                        client.recv(timeout=.02)  # No generated silence or video prerequisite.
                server.broadcast_audio(b'\x01\x00'*160)
                for client in (first, second):
                    pcm = client.recv(timeout=1)
                    assert isinstance(pcm, bytes) and len(pcm) >= 950
                    assert pcm[:2] == b'\x01\x00'
                assert not activate.called and server._active is None
        finally:
            endpoint.shutdown()
            worker.join(2)


def test_slow_microphone_reader_keeps_only_bounded_recent_audio():
    import queue
    server = PcmTalkServer('127.0.0.1', 0, 'secret', 'ebo', Mock(), Mock())
    pending = queue.Queue(maxsize=20)
    server._listeners[object()] = pending
    for n in range(100):
        server.broadcast_audio(bytes([n, 0])*80)
    assert pending.qsize() == 20
    assert pending.get_nowait()[1] == bytes([80, 0])*80
