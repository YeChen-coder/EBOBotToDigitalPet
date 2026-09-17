"""Source health must not be fooled by silence padding or old SDK callbacks."""
from pathlib import Path
from unittest.mock import patch

from audio_health import AudioHealth
from conftest import deliver, _session


def test_pcm_without_new_network_bytes_is_not_live_audio():
    health = AudioHealth()
    with patch("audio_health.time.time", return_value=100):
        health.statistics(100, 73)
        health.pcm()
        assert health.snapshot(True, True)["status"] == "receiving"
    with patch("audio_health.time.time", return_value=121):
        health.statistics(100, 0)
        health.pcm()  # concealment callbacks / silent decoder output keep firing
        assert health.snapshot(True, True)["status"] == "no_source_packets"


def test_quiet_audio_packets_are_healthy_without_volume_test():
    health = AudioHealth()
    health.statistics(100, 0)
    health.pcm()  # no amplitude gate: silence in the room is legitimate
    assert health.snapshot(True, True)["source_audio_ok"]
    assert health.snapshot(False, True)["status"] == "muted"
    assert health.snapshot(True, False)["status"] == "disconnected"
    assert health.snapshot(True, True, enabled=False)["status"] == "disabled"


def test_missing_pcm_and_new_connection():
    health = AudioHealth()
    health.statistics(200, 70)
    assert health.snapshot(True, True)["status"] == "no_decoded_pcm"
    assert AudioHealth().snapshot(True, True)["status"] == "no_source_packets"


def test_global_mute_persists_and_publishes(bridge, B_mod, tmp_path, monkeypatch):
    monkeypatch.setenv("EBO_DATA_DIR", str(tmp_path))
    bridge._ui_path = str(tmp_path / "ui_choices.json")
    bridge.audio_enabled = True
    bridge.rtc_state = "connected"
    deliver(bridge, "ebo/microphone/set", "off")
    assert not bridge.listen_on
    assert (B_mod.OP_AUDIO_LISTEN, {"type": 1, "open": 0}) in bridge.sent
    assert any(topic.endswith("/audio_health") and '"muted"' in payload
               for topic, payload, _retain in bridge.mqtt.published)
    restarted = B_mod.Bridge(_session(), {"host": "h", "port": 1883})
    assert not restarted.listen_on
    deliver(bridge, "ebo/microphone/set", "on")
    assert B_mod.Bridge(_session(), {"host": "h", "port": 1883}).listen_on


def test_legacy_mqtt_listen_never_changes_global_microphone(bridge):
    for current in (True, False):
        bridge.listen_on = current
        bridge.sent.clear()
        for payload in ("on", "off"):
            deliver(bridge, "ebo/listen/set", payload)
            assert bridge.listen_on is current
            assert bridge.sent == []


def test_player_mute_does_not_send_global_command():
    source = (Path(__file__).parents[1] / "panel.py").read_text(encoding="utf-8")
    toggle = source.split("async function toggleListen(node){", 1)[1].split("// ---- Talk", 1)[0]
    assert "v.muted = !want" in toggle
    assert "await cmd(" not in toggle
    assert "listen/set" not in toggle
    assert "机器人麦克风上传（全局隐私开关）" in source


def test_startup_retry_respects_privacy_and_observer_generation():
    source = (Path(__file__).parents[1] / "ebo_bridge.py").read_text(encoding="utf-8")
    recovery = source.split("def _recover_robot_audio", 1)[1].split("def connect_agora", 1)[0]
    assert "self.listen_on" in recovery
    assert "obs is not self._audio_obs" in recovery
    assert "rtc is not self.rtc" in recovery


def test_post_join_audio_recovery_reopens_and_resubscribes_until_pcm(bridge, B_mod):
    class ImmediateStop:
        def __init__(self):
            self.waits = []

        def wait(self, delay):
            self.waits.append(delay)
            return False

    class Observer:
        _n = [0]

    stop = ImmediateStop()
    observer = Observer()
    rtc = object()
    bridge.stop = stop
    bridge.rtc = rtc
    bridge._audio_obs = observer
    bridge.robot_uid = "210010683"
    bridge.audio_enabled = True
    bridge.listen_on = True
    subscriptions = []

    def subscribe(tag):
        subscriptions.append(tag)
        if len(subscriptions) == 2:
            observer._n[0] = 1

    result = bridge._recover_robot_audio(
        "210010683", rtc, observer, subscribe, delays=(0, 0, 0)
    )

    assert result == "receiving"
    assert stop.waits == [0, 0, 0]
    assert subscriptions == ["recovery-1", "recovery-2"]
    assert bridge.sent == [
        (B_mod.OP_AUDIO_LISTEN, {"type": 1, "open": 1}),
        (B_mod.OP_AUDIO_LISTEN, {"type": 1, "open": 1}),
    ]


def test_post_join_audio_recovery_stops_for_privacy_or_stale_session(bridge):
    class ImmediateStop:
        def wait(self, _delay):
            return False

    class Observer:
        _n = [0]

    bridge.stop = ImmediateStop()
    bridge._audio_obs = Observer()
    bridge.rtc = object()
    bridge.robot_uid = "210010683"
    bridge.audio_enabled = True
    bridge.listen_on = False
    subscriptions = []

    assert bridge._recover_robot_audio(
        "210010683", bridge.rtc, bridge._audio_obs, subscriptions.append, delays=(0,)
    ) == "disabled"
    assert bridge.sent == []
    assert subscriptions == []

    bridge.listen_on = True
    stale_rtc = object()
    assert bridge._recover_robot_audio(
        "210010683", stale_rtc, bridge._audio_obs, subscriptions.append, delays=(0,)
    ) == "stale"
    assert bridge.sent == []
    assert subscriptions == []
