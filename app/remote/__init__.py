"""Remote control of playback (local WebSocket API for e.g. a Stream Deck)"""

from .facade import RemoteControlFacade, RemoteError
from .server import DEFAULT_PORT, RemoteControlServer

__all__ = ["DEFAULT_PORT", "RemoteControlFacade", "RemoteControlServer", "RemoteError"]
