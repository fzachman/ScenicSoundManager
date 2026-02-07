"""Tests for the SmartShuffle utility."""

from app.audio.shuffle import SmartShuffle


class TestSmartShuffle:
    def test_empty_tracks_returns_none(self):
        s = SmartShuffle([])
        assert s.next() is None

    def test_none_tracks_returns_none(self):
        s = SmartShuffle()
        assert s.next() is None

    def test_single_track(self):
        s = SmartShuffle([42])
        assert s.next() == 42
        # Exhausted, next call reshuffles and returns same track
        assert s.next() == 42

    def test_all_tracks_played_before_repeat(self):
        track_ids = [1, 2, 3, 4, 5]
        s = SmartShuffle(track_ids)

        played = []
        for _ in range(5):
            played.append(s.next())

        # All tracks should appear exactly once
        assert sorted(played) == sorted(track_ids)

    def test_no_repeats_within_cycle(self):
        track_ids = list(range(1, 21))  # 20 tracks
        s = SmartShuffle(track_ids)

        played = []
        for _ in range(20):
            played.append(s.next())

        assert len(set(played)) == 20
        assert sorted(played) == sorted(track_ids)

    def test_second_cycle_reshuffles(self):
        track_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        s = SmartShuffle(track_ids)

        cycle1 = [s.next() for _ in range(10)]
        cycle2 = [s.next() for _ in range(10)]

        # Both cycles contain all tracks
        assert sorted(cycle1) == sorted(track_ids)
        assert sorted(cycle2) == sorted(track_ids)

    def test_multiple_complete_cycles(self):
        track_ids = [1, 2, 3]
        s = SmartShuffle(track_ids)

        for _ in range(5):  # 5 full cycles
            played = [s.next() for _ in range(3)]
            assert sorted(played) == [1, 2, 3]

    def test_remaining_count(self):
        s = SmartShuffle([1, 2, 3])
        assert s.remaining == 3

        s.next()
        assert s.remaining == 2

        s.next()
        assert s.remaining == 1

        s.next()
        assert s.remaining == 0

    def test_cycle_complete(self):
        s = SmartShuffle([1, 2])
        assert not s.cycle_complete

        s.next()
        assert not s.cycle_complete

        s.next()
        assert s.cycle_complete

    def test_peek_returns_next_without_advancing(self):
        s = SmartShuffle([10, 20, 30])
        first_peek = s.peek()
        second_peek = s.peek()
        actual_next = s.next()

        assert first_peek == second_peek
        assert first_peek == actual_next

    def test_peek_returns_none_when_cycle_exhausted(self):
        s = SmartShuffle([1])
        s.next()
        assert s.peek() is None

    def test_peek_returns_none_when_empty(self):
        s = SmartShuffle([])
        assert s.peek() is None

    def test_reset_reshuffles(self):
        s = SmartShuffle([1, 2, 3, 4, 5])
        s.next()
        s.next()
        assert s.remaining == 3

        s.reset()
        assert s.remaining == 5
        assert not s.cycle_complete

    def test_reset_plays_all_tracks(self):
        track_ids = [1, 2, 3]
        s = SmartShuffle(track_ids)
        s.next()
        s.reset()

        played = [s.next() for _ in range(3)]
        assert sorted(played) == sorted(track_ids)

    def test_update_tracks_resets(self):
        s = SmartShuffle([1, 2, 3])
        s.next()
        s.next()

        s.update_tracks([10, 20, 30, 40])
        assert s.remaining == 4

        played = [s.next() for _ in range(4)]
        assert sorted(played) == [10, 20, 30, 40]

    def test_update_tracks_to_empty(self):
        s = SmartShuffle([1, 2, 3])
        s.update_tracks([])
        assert s.next() is None
        assert s.remaining == 0

    def test_update_tracks_from_empty(self):
        s = SmartShuffle([])
        s.update_tracks([5, 6])
        played = [s.next() for _ in range(2)]
        assert sorted(played) == [5, 6]

    def test_track_ids_property_returns_copy(self):
        original = [1, 2, 3]
        s = SmartShuffle(original)
        ids = s.track_ids
        ids.append(999)
        assert s.track_ids == [1, 2, 3]

    def test_large_playlist_no_repeats(self):
        track_ids = list(range(1, 101))  # 100 tracks
        s = SmartShuffle(track_ids)

        played = [s.next() for _ in range(100)]
        assert len(set(played)) == 100
        assert sorted(played) == sorted(track_ids)

    def test_shuffle_is_randomized(self):
        """Verify shuffle produces different orders (statistical test).

        With 10 tracks, the chance of getting the same order twice
        is 1/10! = 1/3628800, so this is extremely unlikely to flake.
        """
        track_ids = list(range(1, 11))
        orders = set()
        for _ in range(5):
            s = SmartShuffle(track_ids)
            order = tuple(s.next() for _ in range(10))
            orders.add(order)

        # At least 2 different orders out of 5 attempts
        assert len(orders) >= 2
