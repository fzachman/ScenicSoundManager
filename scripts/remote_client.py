#!/usr/bin/env python
"""CLI test client for the SoundManager remote-control protocol.

Doubles as the reference client implementation for external controllers
(e.g. the Stream Deck plugin). Protocol spec: docs/remote-protocol.md.

Usage (with the app running):
    venv/bin/python scripts/remote_client.py state
    venv/bin/python scripts/remote_client.py scenes
    venv/bin/python scripts/remote_client.py playlists
    venv/bin/python scripts/remote_client.py play-scene 3
    venv/bin/python scripts/remote_client.py play-playlist 2
    venv/bin/python scripts/remote_client.py toggle
    venv/bin/python scripts/remote_client.py next
    venv/bin/python scripts/remote_client.py volume 40
    venv/bin/python scripts/remote_client.py watch     # stream state events

Exit status: 0 on ok:true, 1 on protocol error / connection failure / timeout.
"""

import argparse
import json
import signal
import sys

from PyQt6.QtCore import QCoreApplication, QTimer, QUrl
from PyQt6.QtWebSockets import QWebSocket

DEFAULT_PORT = 8765
TIMEOUT_MS = 5000

COMMANDS = {
    "state": ("get_state", None),
    "scenes": ("get_scenes", None),
    "playlists": ("get_playlists", None),
    "play-scene": ("play_scene", "scene_id"),
    "play-playlist": ("play_playlist", "playlist_id"),
    "toggle": ("toggle_play_pause", None),
    "next": ("next_track", None),
    "volume": ("set_master_volume", "value"),
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("command", choices=[*COMMANDS, "watch"])
    parser.add_argument("value", nargs="?", type=int, help="id / volume value")
    args = parser.parse_args()
    if args.command != "watch":
        _, param = COMMANDS[args.command]
        if param is not None and args.value is None:
            parser.error(f"'{args.command}' requires a value")
    return args


def main() -> int:
    args = parse_args()
    app = QCoreApplication(sys.argv)
    exit_code = 1
    socket = QWebSocket()

    def finish(code: int):
        nonlocal exit_code
        exit_code = code
        socket.close()
        app.quit()

    def on_connected():
        if args.command == "watch":
            print("watching state events (Ctrl+C to stop)...", flush=True)
            return
        cmd, param = COMMANDS[args.command]
        params = {param: args.value} if param is not None else {}
        socket.sendTextMessage(json.dumps({"id": 1, "cmd": cmd, "params": params}))

    def on_message(text: str):
        message = json.loads(text)
        if args.command == "watch":
            print(json.dumps(message), flush=True)
            return
        if "ok" not in message:  # unsolicited state event; keep waiting
            return
        print(json.dumps(message, indent=2))
        finish(0 if message["ok"] else 1)

    def on_error(_error):
        print(f"connection failed: {socket.errorString()}", file=sys.stderr)
        finish(1)

    def on_timeout():
        print("timed out waiting for a response", file=sys.stderr)
        finish(1)

    # Python's KeyboardInterrupt can't be delivered while Qt's C++ event loop
    # is idle (it just queues, then aborts the process when the next slot runs).
    # Restore the OS default so Ctrl+C terminates immediately — nothing here
    # needs graceful cleanup.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    socket.connected.connect(on_connected)
    socket.textMessageReceived.connect(on_message)
    socket.errorOccurred.connect(on_error)
    if args.command != "watch":
        QTimer.singleShot(TIMEOUT_MS, on_timeout)
    socket.open(QUrl(f"ws://127.0.0.1:{args.port}"))
    app.exec()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
