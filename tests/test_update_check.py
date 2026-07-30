"""Tests for the GitHub-releases update check (app/update_check.py)."""

from app.update_check import Release, find_newer_release


def _release(tag, draft=False, url="https://example.com/r"):
    return {"tag_name": tag, "draft": draft, "html_url": url}


class TestFindNewerRelease:
    def test_newer_release_found(self):
        result = find_newer_release([_release("v0.9.1")], "0.9.0")
        assert result == Release(version="0.9.1", url="https://example.com/r")

    def test_same_version_is_not_an_update(self):
        assert find_newer_release([_release("v0.9.0")], "0.9.0") is None

    def test_older_release_ignored(self):
        assert find_newer_release([_release("v0.8.9")], "0.9.0") is None

    def test_newest_of_several_wins_regardless_of_order(self):
        releases = [
            _release("v0.9.1", url="https://example.com/091"),
            _release("v1.0.0", url="https://example.com/100"),
            _release("v0.9.2", url="https://example.com/092"),
        ]
        result = find_newer_release(releases, "0.9.0")
        assert result is not None
        assert result.version == "1.0.0"
        assert result.url == "https://example.com/100"

    def test_draft_releases_skipped(self):
        assert find_newer_release([_release("v9.9.9", draft=True)], "0.9.0") is None

    def test_unparseable_tag_skipped(self):
        releases = [_release("nightly-build"), _release("v0.9.1")]
        result = find_newer_release(releases, "0.9.0")
        assert result is not None
        assert result.version == "0.9.1"

    def test_unparseable_current_version_disables_check(self):
        assert find_newer_release([_release("v9.9.9")], "dev") is None

    def test_minor_vs_patch_ordering(self):
        # 0.10.0 > 0.9.1 numerically, not lexically.
        result = find_newer_release([_release("v0.10.0")], "0.9.1")
        assert result is not None
        assert result.version == "0.10.0"

    def test_longer_tag_beats_shorter_prefix(self):
        result = find_newer_release([_release("v0.9.0.1")], "0.9.0")
        assert result is not None
        assert result.version == "0.9.0.1"

    def test_empty_release_list(self):
        assert find_newer_release([], "0.9.0") is None
