"""Local WebSocket server exposing the remote-control protocol.

Runs entirely on the Qt event loop via ``QWebSocketServer`` — command handlers
may therefore call facade/widget methods directly, with no cross-thread
marshaling. Binds to localhost only. Wire protocol: ``docs/remote-protocol.md``.

PyQt6 aborts the process on an exception escaping a slot invoked from C++, so
every socket-driven entry point here is defensively wrapped: a bad message can
only ever produce an ``ok: false`` response, never a crash.
"""

import json

from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtNetwork import QHostAddress
from PyQt6.QtWebSockets import QWebSocket, QWebSocketServer

from ..shared.logging import get_logger
from .facade import RemoteControlFacade, RemoteError

logger = get_logger(__name__)

DEFAULT_PORT = 8765


def _error(req_id, code: str, message: str) -> dict:
    return {"id": req_id, "ok": False, "error": {"code": code, "message": message}}


class RemoteControlServer(QObject):
    """Accepts localhost WebSocket clients and bridges them to the facade."""

    def __init__(
        self, facade: RemoteControlFacade, port: int = DEFAULT_PORT, parent=None
    ):
        super().__init__(parent)
        self._facade = facade
        self._port = port
        self._clients: list[QWebSocket] = []
        self._server = QWebSocketServer(
            "SoundManager Remote", QWebSocketServer.SslMode.NonSecureMode, self
        )
        self._server.newConnection.connect(self._on_new_connection)
        facade.state_changed.connect(self._broadcast_state)
        self._commands = {
            "get_state": lambda p: self._facade.get_state(),
            "get_scenes": lambda p: self._facade.get_scenes(),
            "get_playlists": lambda p: self._facade.get_playlists(),
            "play_scene": lambda p: self._facade.play_scene(p.get("scene_id")),
            "play_playlist": lambda p: self._facade.play_playlist(p.get("playlist_id")),
            "toggle_play_pause": lambda p: self._facade.toggle_play_pause(),
            "next_track": lambda p: self._facade.next_track(),
            "set_master_volume": lambda p: {
                "master_volume": self._facade.set_master_volume(p.get("value"))
            },
        }

    def start(self) -> bool:
        """Bind and listen; False (with a warning) on failure — never raises,
        so a port collision can't prevent the app from starting."""
        address = QHostAddress(QHostAddress.SpecialAddress.LocalHost)
        if not self._server.listen(address, self._port):
            logger.warning(
                "remote_server_bind_failed",
                port=self._port,
                error=self._server.errorString(),
            )
            return False
        logger.info("remote_server_listening", port=self._server.serverPort())
        return True

    def stop(self):
        clients, self._clients = self._clients, []
        for client in clients:
            # abort(), not close(): close() starts an async close handshake
            # the app's exit would destroy mid-flight. Localhost controllers
            # just see a dropped connection either way and reconnect.
            client.abort()
            # Destroy the socket synchronously: left to QApplication teardown
            # (deleteLater never runs once the loop is exiting), destruction
            # happens during interpreter shutdown, after logging is gone. A
            # QWebSocket's destructor intrinsically emits Qt wildcard-
            # disconnect warnings; destroying it here keeps those inside the
            # configured Qt message handler's lifetime (see shared/logging.py).
            sip.delete(client)
        self._server.close()

    @property
    def port(self) -> int:
        """The bound port (useful when constructed with port 0 in tests)."""
        return self._server.serverPort()

    # --- connection lifecycle ----------------------------------------------

    def _on_new_connection(self):
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        self._clients.append(socket)
        socket.textMessageReceived.connect(
            lambda message, s=socket: self._on_message(s, message)
        )
        socket.disconnected.connect(lambda s=socket: self._on_disconnected(s))
        logger.info("remote_client_connected", clients=len(self._clients))
        self._send(socket, {"event": "state", "data": self._facade.get_state()})

    def _on_disconnected(self, socket):
        if socket in self._clients:
            self._clients.remove(socket)
        socket.deleteLater()
        logger.info("remote_client_disconnected", clients=len(self._clients))

    # --- request handling ----------------------------------------------------

    def _on_message(self, socket, message: str):
        try:
            response = self._handle(message)
        except Exception:
            logger.exception("remote_handler_error")
            response = _error(None, "internal_error", "internal error")
        self._send(socket, response)

    def _handle(self, message: str) -> dict:
        try:
            request = json.loads(message)
        except json.JSONDecodeError:
            return _error(None, "bad_request", "message is not valid JSON")
        if not isinstance(request, dict):
            return _error(None, "bad_request", "message must be a JSON object")
        req_id = request.get("id")
        params = request.get("params") or {}
        if not isinstance(params, dict):
            return _error(req_id, "bad_request", "params must be an object")
        cmd = request.get("cmd")
        handler = self._commands.get(cmd) if isinstance(cmd, str) else None
        if handler is None:
            return _error(req_id, "unknown_command", f"unknown command: {cmd!r}")
        try:
            result = handler(params)
        except RemoteError as exc:
            return _error(req_id, exc.code, exc.message)
        return {"id": req_id, "ok": True, "result": result}

    # --- outbound -------------------------------------------------------------

    def _broadcast_state(self, state):
        payload = {"event": "state", "data": state}
        for client in self._clients:
            self._send(client, payload)

    def _send(self, socket, payload: dict):
        try:
            socket.sendTextMessage(json.dumps(payload))
        except Exception:
            logger.exception("remote_send_failed")
