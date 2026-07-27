"""In-process end-to-end tests for RemoteControlServer (Plan 007 Phase 2).

A real QWebSocket client talks to a real server (ephemeral port) backed by a
real MainWindow, all on the offscreen QApplication's event loop — network I/O
is pumped by processEvents, no threads and no extra dependencies.
"""

import gc
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, QUrl
from PyQt6.QtNetwork import QAbstractSocket
from PyQt6.QtWebSockets import QWebSocket

import app.main_window as main_window_module
from app.database import AudioFile, DatabaseConnection, Scene, Soundboard
from app.remote.server import RemoteControlServer


@pytest.fixture(autouse=True)
def _deterministic_qt_teardown(qapp):
    """Destroy leftover Qt objects at the test boundary, not mid-test.

    Without this, a QWebSocket/QWebSocketServer from a finished test can be
    garbage-collected while the next test is constructing its MainWindow;
    C++-side destruction during an arbitrary GC pass aborts the process
    ("Fatal Python error: Aborted"). Pump pending deleteLater events and
    collect while the loop is idle instead.
    """
    yield
    qapp.processEvents()
    gc.collect()
    qapp.processEvents()


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(
        main_window_module,
        "DatabaseConnection",
        lambda **kw: DatabaseConnection(db_path),
    )
    window = main_window_module.MainWindow()
    yield window
    window.db.close()


@pytest.fixture
def server(main_window):
    srv = RemoteControlServer(main_window.remote_facade, port=0)
    assert srv.start()
    yield srv
    srv.stop()


def _wait_until(qapp, predicate, what="condition", timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail(f"timed out waiting for {what}")
        qapp.processEvents()


class Client:
    """Tiny test client: records every inbound frame, parsed."""

    def __init__(self, qapp, server):
        self.qapp = qapp
        self.socket = QWebSocket()
        self.messages = []
        self.socket.textMessageReceived.connect(
            lambda m: self.messages.append(json.loads(m))
        )
        self.socket.open(QUrl(f"ws://127.0.0.1:{server.port}"))
        _wait_until(
            qapp,
            lambda: self.socket.state() == QAbstractSocket.SocketState.ConnectedState,
            "client connect",
        )
        # Every connection starts with a state snapshot event.
        _wait_until(qapp, lambda: len(self.messages) >= 1, "initial snapshot")

    def request(self, cmd, params=None, req_id=1):
        """Send a command and return its response (skipping state events)."""
        self.send_raw(json.dumps({"id": req_id, "cmd": cmd, "params": params or {}}))
        return self.wait_response(req_id)

    def send_raw(self, text):
        self.socket.sendTextMessage(text)

    def wait_response(self, req_id):
        def find():
            for message in self.messages:
                if "ok" in message and message.get("id") == req_id:
                    return message
            return None

        _wait_until(self.qapp, lambda: find() is not None, f"response id={req_id}")
        return find()

    def state_events(self):
        return [m for m in self.messages if m.get("event") == "state"]

    def close(self):
        """Close and fully tear down the socket while the loop is pumping."""
        self.socket.close()
        deadline = time.monotonic() + 2.0
        while (
            self.socket.state() != QAbstractSocket.SocketState.UnconnectedState
            and time.monotonic() < deadline
        ):
            self.qapp.processEvents()
        self.socket.deleteLater()
        self.qapp.processEvents()


@pytest.fixture
def client(qapp, server):
    c = Client(qapp, server)
    yield c
    c.close()


# --- connection & snapshot ----------------------------------------------------


def test_connect_receives_initial_state_snapshot(client):
    snapshot = client.messages[0]
    assert snapshot["event"] == "state"
    assert "playing" in snapshot["data"]
    assert isinstance(snapshot["data"]["master_volume"], int)


def test_get_state_round_trip(client):
    response = client.request("get_state", req_id=7)
    assert response["id"] == 7
    assert response["ok"] is True
    assert response["result"]["playing"] is None


def test_get_scenes_round_trip(main_window, client):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    response = client.request("get_scenes")
    assert response["ok"] is True
    (scene,) = [s for s in response["result"] if s["id"] == scene_id]
    assert scene["name"] == "Tavern"
    assert scene["active_preset"] == 1
    assert scene["presets"] == [
        {"slot": 1, "name": None},
        {"slot": 2, "name": None},
        {"slot": 3, "name": None},
    ]


# --- commands -------------------------------------------------------------------


def test_play_scene_dispatches_to_widgets(main_window, client, monkeypatch):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    selected, played = [], []
    monkeypatch.setattr(
        main_window.scenes_widget, "select_scene", lambda i: selected.append(i)
    )
    monkeypatch.setattr(
        main_window.scenes_widget, "play_current", lambda: played.append(True)
    )
    response = client.request("play_scene", {"scene_id": scene_id})
    assert response["ok"] is True
    assert selected == [scene_id]
    assert played == [True]


def test_play_scene_forwards_preset_param(main_window, client, monkeypatch):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    switched = []
    monkeypatch.setattr(
        main_window.scenes_widget, "switch_preset", lambda s: switched.append(s)
    )
    monkeypatch.setattr(main_window.scenes_widget, "play_current", lambda: None)
    response = client.request("play_scene", {"scene_id": scene_id, "preset": 2})
    assert response["ok"] is True
    assert switched == [2]


def test_set_preset_dispatches_to_active_scene(main_window, client, monkeypatch):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    editor = main_window.scenes_widget.scene_editor
    editor._active_scene_id = scene_id
    editor._scene_playing = True
    switched = []
    monkeypatch.setattr(
        main_window.scenes_widget, "switch_preset", lambda s: switched.append(s)
    )
    response = client.request("set_preset", {"preset": 3})
    assert response["ok"] is True
    assert switched == [3]


def test_set_preset_idle_errors_no_active_scene(client):
    response = client.request("set_preset", {"preset": 2})
    assert response["ok"] is False
    assert response["error"]["code"] == "no_active_scene"


def test_play_scene_unknown_id_errors(client):
    response = client.request("play_scene", {"scene_id": 999})
    assert response["ok"] is False
    assert response["error"]["code"] == "not_found"


def test_play_scene_missing_param_errors(client):
    response = client.request("play_scene")
    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_params"


def test_toggle_play_pause_dispatches(main_window, client, monkeypatch):
    calls = []
    monkeypatch.setattr(main_window, "toggle_play_pause", lambda: calls.append(True))
    assert client.request("toggle_play_pause")["ok"] is True
    assert calls == [True]


def test_set_master_volume_applies_and_clamps(main_window, client):
    response = client.request("set_master_volume", {"value": 150})
    assert response["ok"] is True
    assert response["result"] == {"master_volume": 100}
    assert main_window.master_slider.value() == 100


def _make_button(main_window, tmp_path) -> int:
    """A soundboard button whose audio file really exists on disk."""
    sfx = tmp_path / "hit.wav"
    sfx.write_bytes(b"\x00")
    file_id = main_window.db.add_audio_file(
        AudioFile(file_path=str(sfx), title="Sword Clash")
    )
    board_id = main_window.db.add_soundboard(Soundboard(name="Combat"))
    return main_window.db.add_button_to_soundboard(board_id, file_id)


def test_get_soundboards_round_trip(main_window, client, tmp_path):
    button_id = _make_button(main_window, tmp_path)
    response = client.request("get_soundboards")
    assert response["ok"] is True
    (board,) = response["result"]
    assert board["name"] == "Combat"
    assert board["buttons"] == [{"id": button_id, "name": "Sword Clash"}]


def test_trigger_sound_dispatches_to_player(main_window, client, tmp_path, monkeypatch):
    button_id = _make_button(main_window, tmp_path)
    triggered = []
    monkeypatch.setattr(
        main_window.soundboard_player, "trigger", lambda *a: triggered.append(a)
    )
    response = client.request("trigger_sound", {"button_id": button_id})
    assert response["ok"] is True
    assert triggered == [(button_id, str(tmp_path / "hit.wav"), 1.0)]


def test_trigger_sound_missing_param_errors(client):
    response = client.request("trigger_sound")
    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_params"


def test_stop_sound_round_trip(main_window, client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        main_window.soundboard_player, "stop", lambda: calls.append(True)
    )
    assert client.request("stop_sound")["ok"] is True
    assert calls == [True]


def test_sound_start_broadcasts_state(main_window, qapp, client, tmp_path):
    button_id = _make_button(main_window, tmp_path)
    player = main_window.soundboard_player
    before = len(client.state_events())
    player._current_button_id = button_id
    player.button_started.emit(button_id)
    _wait_until(qapp, lambda: len(client.state_events()) > before, "sound state event")
    sound = client.state_events()[-1]["data"]["sound"]
    assert sound["button_id"] == button_id
    assert sound["name"] == "Sword Clash"


# --- malformed input never crashes or disconnects --------------------------------


def test_invalid_json_gets_bad_request_and_connection_survives(client):
    client.send_raw("{not json")
    response = client.wait_response(None)
    assert response["ok"] is False
    assert response["error"]["code"] == "bad_request"
    # Connection still usable afterwards.
    assert client.request("get_state", req_id=2)["ok"] is True


def test_non_object_json_is_bad_request(client):
    client.send_raw("[1, 2, 3]")
    response = client.wait_response(None)
    assert response["error"]["code"] == "bad_request"


def test_non_object_params_is_bad_request(client):
    client.send_raw(json.dumps({"id": 3, "cmd": "get_state", "params": [1]}))
    response = client.wait_response(3)
    assert response["error"]["code"] == "bad_request"


def test_unknown_command_errors(client):
    response = client.request("self_destruct")
    assert response["ok"] is False
    assert response["error"]["code"] == "unknown_command"


def test_handler_exception_becomes_internal_error(main_window, client, monkeypatch):
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(main_window.remote_facade, "get_state", boom)
    client.send_raw(json.dumps({"id": 4, "cmd": "get_state"}))
    # The response's id is not preserved through the defensive catch-all.
    response = client.wait_response(None)
    assert response["ok"] is False
    assert response["error"]["code"] == "internal_error"


# --- broadcasts --------------------------------------------------------------------


def test_playback_change_broadcasts_state_to_all_clients(
    main_window, qapp, server, client
):
    other = Client(qapp, server)
    try:
        scene_id = main_window.db.add_scene(Scene(title="Tavern"))
        main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", True)

        def got_playing(c):
            return any(
                (e["data"]["playing"] or {}).get("id") == scene_id
                for e in c.state_events()
            )

        _wait_until(qapp, lambda: got_playing(client), "client 1 broadcast")
        _wait_until(qapp, lambda: got_playing(other), "client 2 broadcast")
        event = client.state_events()[-1]
        assert event["data"]["playing"]["name"] == "Tavern"
    finally:
        other.close()


def test_pause_broadcasts_paused_state(main_window, qapp, client):
    # A pause (is_playing=False with the id still set, editor still active)
    # must reach clients as paused, not as idle.
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", True)
    editor = main_window.scenes_widget.scene_editor
    editor._active_scene_id = scene_id
    editor._scene_playing = False
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", False)

    def got_paused():
        return any(
            (e["data"].get("paused") or {}).get("id") == scene_id
            for e in client.state_events()
        )

    _wait_until(qapp, got_paused, "paused broadcast")
    event = client.state_events()[-1]
    assert event["data"]["playing"] is None
    assert event["data"]["paused"] == {
        "type": "scene",
        "id": scene_id,
        "name": "Tavern",
        "preset": {"slot": 1, "name": None},
    }


def test_volume_change_broadcasts_state(main_window, qapp, client):
    main_window.master_slider.setValue(33)
    _wait_until(
        qapp,
        lambda: any(e["data"]["master_volume"] == 33 for e in client.state_events()),
        "volume broadcast",
    )


def test_disconnected_client_is_dropped(main_window, qapp, server, client):
    other = Client(qapp, server)
    other.close()
    _wait_until(qapp, lambda: len(server._clients) == 1, "client removal")
    # Broadcasting after a disconnect must not raise.
    main_window.master_slider.setValue(44)
    _wait_until(
        qapp,
        lambda: any(e["data"]["master_volume"] == 44 for e in client.state_events()),
        "post-disconnect broadcast",
    )


# --- bind failure ---------------------------------------------------------------


def test_bind_failure_returns_false(main_window, server):
    duplicate = RemoteControlServer(main_window.remote_facade, port=server.port)
    assert duplicate.start() is False


# --- MainWindow wiring (QSettings: remote/enabled, remote/port) --------------------


def _set_remote_settings(enabled: bool, port=None):
    settings = QSettings()
    settings.beginGroup("remote")
    settings.setValue("enabled", enabled)
    if port is not None:
        settings.setValue("port", port)
    settings.endGroup()


@pytest.fixture
def remote_enabled(qapp):
    # Ephemeral port: wiring tests must not depend on 8765 being free.
    _set_remote_settings(True, port=0)
    yield
    _set_remote_settings(False)


def test_main_window_starts_server_when_enabled(
    qapp, tmp_path, monkeypatch, remote_enabled
):
    db_path = str(tmp_path / "wired.db")
    monkeypatch.setattr(
        main_window_module,
        "DatabaseConnection",
        lambda **kw: DatabaseConnection(db_path),
    )
    window = main_window_module.MainWindow()
    try:
        assert window.remote_server is not None
        assert window.remote_server.port > 0
        connected = Client(qapp, window.remote_server)
        try:
            assert connected.request("get_state")["ok"] is True
        finally:
            connected.close()
    finally:
        if window.remote_server is not None:
            window.remote_server.stop()
        window.db.close()


def test_main_window_skips_server_when_disabled(main_window):
    # conftest turns remote/enabled off in the test settings namespace.
    assert main_window.remote_server is None
