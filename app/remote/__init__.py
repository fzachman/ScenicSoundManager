"""Remote control of playback (local WebSocket API for e.g. a Stream Deck)"""

from .facade import RemoteControlFacade, RemoteError

__all__ = ["RemoteControlFacade", "RemoteError"]
