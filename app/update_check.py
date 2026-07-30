"""Startup update check against GitHub Releases.

Notify-only by design: the app is unsigned during the beta, so it must
never replace itself — we just point the user at the release page.
Queries the releases LIST endpoint because /releases/latest excludes
prereleases, and every beta version is one. Any failure (offline, rate
limit, malformed payload) is logged and swallowed; startup never blocks
on this.
"""

import json
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import __version__
from .shared.logging import get_logger

logger = get_logger(__name__)

RELEASES_API_URL = (
    "https://api.github.com/repos/fzachman/ScenicSoundManager/releases?per_page=10"
)


@dataclass
class Release:
    version: str  # tag without the leading "v", e.g. "0.9.1"
    url: str  # release page for humans


def _version_tuple(version: str) -> tuple[int, ...] | None:
    """Parse "v0.9.1"/"0.9.1" into (0, 9, 1); None if not purely numeric."""
    try:
        return tuple(int(part) for part in version.lstrip("vV").split("."))
    except ValueError:
        return None


def find_newer_release(releases: list[dict], current: str) -> Release | None:
    """Return the newest non-draft release strictly newer than ``current``.

    Prereleases count (during the beta, every release is one). Entries with
    unparseable tags are skipped rather than guessed at.
    """
    best_version = _version_tuple(current)
    if best_version is None:
        return None
    best: Release | None = None
    for entry in releases:
        if entry.get("draft"):
            continue
        tag = entry.get("tag_name") or ""
        version = _version_tuple(tag)
        if version is None or version <= best_version:
            continue
        best = Release(version=tag.lstrip("vV"), url=entry.get("html_url") or "")
        best_version = version
    return best


class UpdateChecker(QObject):
    """Fetches the release list and emits ``update_available`` if one is newer.

    Emits at most once per ``check()`` call and stays silent on every kind
    of failure.
    """

    update_available = pyqtSignal(object)  # Release

    def __init__(self, current_version: str = __version__, parent=None):
        super().__init__(parent)
        self._current = current_version
        self._manager = QNetworkAccessManager(self)

    def check(self) -> None:
        request = QNetworkRequest(QUrl(RELEASES_API_URL))
        request.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader,
            f"ScenicSoundManager/{self._current}",
        )
        reply = self._manager.get(request)
        if reply is None:  # pragma: no cover - Qt returns None only on OOM
            return
        reply.finished.connect(lambda: self._on_finished(reply))

    def _on_finished(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                logger.info("update_check_failed", error=reply.errorString())
                return
            releases = json.loads(bytes(reply.readAll().data()))
            if not isinstance(releases, list):
                return
            release = find_newer_release(releases, self._current)
            if release is not None:
                logger.info("update_available", version=release.version)
                self.update_available.emit(release)
        except Exception as e:  # noqa: BLE001 - untrusted payload, never crash startup
            logger.info("update_check_failed", error=str(e))
        finally:
            reply.deleteLater()
