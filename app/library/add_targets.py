"""Target kinds for the library's "Add to …" menus, plus their toast text."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetKind:
    """A kind of container the library can add files to."""

    key: str  # signal payload and message word, e.g. "playlist"
    title: str  # menu word, e.g. "Playlist"
    noun: str  # what the container holds, e.g. "track"


PLAYLIST = TargetKind("playlist", "Playlist", "track")
SCENE = TargetKind("scene", "Scene", "track")
SOUNDBOARD = TargetKind("soundboard", "Soundboard", "sound")
KINDS = {kind.key: kind for kind in (PLAYLIST, SCENE, SOUNDBOARD)}


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'s' if n != 1 else ''}"


def added_message(kind: TargetKind, name: str, added: int, requested: int) -> str:
    """Confirmation after adding ``requested`` files, ``added`` of them new."""
    target = f"{kind.key} “{name}”"
    if added == 0:
        if requested == 1:
            return f"Already in {target}"
        return f"All {_count(requested, kind.noun)} already in {target}"
    if requested == 1:
        return f"Added to {target}"
    message = f"Added {_count(added, kind.noun)} to {target}"
    if added < requested:
        message += f" ({requested - added} already there)"
    return message


def created_message(kind: TargetKind, name: str, added: int) -> str:
    """Confirmation after creating a container holding ``added`` files."""
    return f"Created {kind.key} “{name}” with {_count(added, kind.noun)}"
