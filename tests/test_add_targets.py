"""Tests for the library "Add to …" toast wording."""

import pytest

from app.library.add_targets import (
    PLAYLIST,
    SCENE,
    SOUNDBOARD,
    added_message,
    created_message,
)


@pytest.mark.parametrize(
    ("added", "requested", "expected"),
    [
        (1, 1, "Added to playlist “Battle Mix”"),
        (3, 3, "Added 3 tracks to playlist “Battle Mix”"),
        (2, 3, "Added 2 tracks to playlist “Battle Mix” (1 already there)"),
        (1, 2, "Added 1 track to playlist “Battle Mix” (1 already there)"),
        (0, 1, "Already in playlist “Battle Mix”"),
        (0, 3, "All 3 tracks already in playlist “Battle Mix”"),
    ],
)
def test_added_message(added, requested, expected):
    assert added_message(PLAYLIST, "Battle Mix", added, requested) == expected


def test_messages_name_the_kind_and_its_noun():
    # Same-named playlist and scene are told apart by the kind word;
    # soundboards hold sounds, not tracks.
    assert added_message(SCENE, "Tavern", 1, 1) == "Added to scene “Tavern”"
    assert (
        added_message(SOUNDBOARD, "Doors", 2, 2)
        == "Added 2 sounds to soundboard “Doors”"
    )


def test_created_message():
    assert (
        created_message(PLAYLIST, "Boss Fight", 3)
        == "Created playlist “Boss Fight” with 3 tracks"
    )
    assert (
        created_message(SOUNDBOARD, "Spells", 1)
        == "Created soundboard “Spells” with 1 sound"
    )
