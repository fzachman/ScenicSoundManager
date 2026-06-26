"""Smart shuffle utility for playlists.

Provides a shuffle sequence that plays all tracks before repeating any.
When the sequence is exhausted, it reshuffles for the next cycle.
"""

import random


class SmartShuffle:
    """Generates a shuffled play order with no repeats until all items played.

    Usage:
        shuffle = SmartShuffle(track_ids=[1, 2, 3, 4, 5])
        next_id = shuffle.next()       # returns a track id
        shuffle.reset()                # start over with a new shuffle
        shuffle.update_tracks([1, 2])  # change the track list
    """

    def __init__(self, track_ids: list[int] | None = None):
        self._track_ids: list[int] = list(track_ids) if track_ids else []
        self._sequence: list[int] = []
        self._index: int = 0
        if self._track_ids:
            self._reshuffle()

    @property
    def track_ids(self) -> list[int]:
        return list(self._track_ids)

    def _reshuffle(self) -> None:
        """Create a new shuffled sequence from current track IDs."""
        self._sequence = list(self._track_ids)
        random.shuffle(self._sequence)
        self._index = 0

    def next(self) -> int | None:
        """Return the next track ID in the shuffled sequence.

        Returns None if there are no tracks.
        When the sequence is exhausted, reshuffles and starts a new cycle.
        """
        if not self._sequence:
            return None

        if self._index >= len(self._sequence):
            self._reshuffle()

        track_id = self._sequence[self._index]
        self._index += 1
        return track_id

    def peek(self) -> int | None:
        """Return the next track ID without advancing the position."""
        if not self._sequence:
            return None
        if self._index >= len(self._sequence):
            return None  # cycle exhausted; next() will reshuffle
        return self._sequence[self._index]

    @property
    def remaining(self) -> int:
        """Number of tracks remaining in the current cycle."""
        if not self._sequence:
            return 0
        return max(0, len(self._sequence) - self._index)

    @property
    def cycle_complete(self) -> bool:
        """True if all tracks in the current cycle have been played."""
        return self._index >= len(self._sequence)

    def reset(self) -> None:
        """Reset and reshuffle the sequence."""
        if self._track_ids:
            self._reshuffle()
        else:
            self._sequence = []
            self._index = 0

    def update_tracks(self, track_ids: list[int]) -> None:
        """Update the track list and reset the shuffle.

        Use this when tracks are added to or removed from a playlist.
        """
        self._track_ids = list(track_ids)
        if self._track_ids:
            self._reshuffle()
        else:
            self._sequence = []
            self._index = 0
