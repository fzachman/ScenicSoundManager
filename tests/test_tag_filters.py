"""Regression tests for tag-based UI filters."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from app.database import AudioFile, DatabaseConnection, Tag
from app.library.tag_manager import NO_TAG_ID, TagBadge, TagManager
from app.shared.dialogs import AudioFileSearchDialog, FileSelectItem


@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = DatabaseConnection(db_path)
    conn.connect()

    yield conn

    conn.close()
    os.unlink(db_path)


def _find_badge(widget: TagManager, tag_name: str) -> TagBadge:
    for badge in widget.findChildren(TagBadge):
        if badge.tag.name == tag_name:
            return badge
    raise AssertionError(f"Badge not found: {tag_name}")


def _click(widget, qapp):
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    qapp.processEvents()


def _right_click(widget, qapp):
    QTest.mouseClick(widget, Qt.MouseButton.RightButton)
    qapp.processEvents()


@pytest.fixture
def tagged_library(db):
    """Two tags across three files: both, combat-only, urban-only."""
    combat = Tag(name="Combat", color="#FF0000")
    combat.id = db.add_tag(combat)
    urban = Tag(name="Urban", color="#00FF00")
    urban.id = db.add_tag(urban)

    def add(title, *tags):
        file_id = db.add_audio_file(AudioFile(file_path=f"/{title}.mp3", title=title))
        for tag in tags:
            db.add_tag_to_audio_file(file_id, tag.id)
        return file_id

    return {
        "combat": combat,
        "urban": urban,
        "both": add("Both", combat, urban),
        "combat_only": add("Combat Only", combat),
        "urban_only": add("Urban Only", urban),
    }


def test_tag_manager_toggle_does_not_accumulate_stale_badges(db, qapp):
    file_one = db.add_audio_file(AudioFile(file_path="/combat.mp3", title="Combat"))
    file_two = db.add_audio_file(AudioFile(file_path="/urban.mp3", title="Urban"))

    combat = Tag(name="Combat", color="#FF0000")
    combat.id = db.add_tag(combat)
    urban = Tag(name="Urban", color="#00FF00")
    urban.id = db.add_tag(urban)

    db.add_tag_to_audio_file(file_one, combat.id)
    db.add_tag_to_audio_file(file_two, urban.id)

    manager = TagManager(db, allow_manage=True)
    manager.show()
    qapp.processEvents()

    assert len(manager.findChildren(TagBadge)) == 3

    _click(_find_badge(manager, "Combat"), qapp)
    assert set(manager.get_selected_tag_ids()) == {combat.id}
    assert len(manager.findChildren(TagBadge)) == 3

    _click(_find_badge(manager, "Combat"), qapp)
    assert manager.get_selected_tag_ids() == []
    assert len(manager.findChildren(TagBadge)) == 3

    _click(_find_badge(manager, "Urban"), qapp)
    assert set(manager.get_selected_tag_ids()) == {urban.id}
    assert len(manager.findChildren(TagBadge)) == 3


def test_tag_manager_refresh_keeps_hit_testing_on_visible_badges(db, qapp):
    names = ["Combat", "Ambient", "Wilderness", "Urban Interior", "Storm"]
    tags = []
    for idx, name in enumerate(names):
        tag = Tag(name=name, color=f"#{idx + 1:02X}3456")
        tag.id = db.add_tag(tag)
        tags.append(tag)

    manager = TagManager(db, allow_manage=True)
    manager.resize(280, 200)
    manager.show()
    qapp.processEvents()

    initial_height = manager.tags_container.height()
    assert initial_height > 1

    combat_badge = _find_badge(manager, "Combat")
    manager._toggle_tag_filter(combat_badge.tag)
    qapp.processEvents()

    wilderness_badge = _find_badge(manager, "Wilderness")
    assert manager.tags_container.height() > 1
    assert wilderness_badge.width() == wilderness_badge.sizeHint().width()
    assert wilderness_badge.height() == wilderness_badge.sizeHint().height()


def test_audio_file_search_dialog_tag_filter_recovers_after_toggle(db, qapp):
    file_one = db.add_audio_file(AudioFile(file_path="/combat.mp3", title="Combat"))
    file_two = db.add_audio_file(AudioFile(file_path="/urban.mp3", title="Urban"))

    combat = Tag(name="Combat", color="#FF0000")
    combat.id = db.add_tag(combat)
    urban = Tag(name="Urban", color="#00FF00")
    urban.id = db.add_tag(urban)

    db.add_tag_to_audio_file(file_one, combat.id)
    db.add_tag_to_audio_file(file_two, urban.id)

    dialog = AudioFileSearchDialog(db, audio_engine=None)
    dialog.show()
    qapp.processEvents()

    assert len(dialog.findChildren(FileSelectItem)) == 2

    _click(_find_badge(dialog.tag_manager, "Combat"), qapp)
    assert set(dialog.tag_manager.get_selected_tag_ids()) == {combat.id}
    assert len(dialog.findChildren(FileSelectItem)) == 1

    _click(_find_badge(dialog.tag_manager, "Combat"), qapp)
    assert dialog.tag_manager.get_selected_tag_ids() == []
    assert len(dialog.findChildren(FileSelectItem)) == 2

    _click(_find_badge(dialog.tag_manager, "Urban"), qapp)
    assert set(dialog.tag_manager.get_selected_tag_ids()) == {urban.id}
    items = dialog.findChildren(FileSelectItem)
    assert len(items) == 1
    assert items[0].file.id == file_two


class TestTagExclusion:
    """Right-click exclusion + tri-state badge behavior in TagManager."""

    def test_right_click_excludes_tag(self, db, tagged_library, qapp):
        manager = TagManager(db, allow_manage=False)
        manager.show()
        qapp.processEvents()

        _right_click(_find_badge(manager, "Urban"), qapp)

        assert manager.get_excluded_tag_ids() == [tagged_library["urban"].id]
        assert manager.get_selected_tag_ids() == []

    def test_left_click_on_excluded_returns_to_neutral(self, db, tagged_library, qapp):
        manager = TagManager(db, allow_manage=False)
        manager.show()
        qapp.processEvents()

        _right_click(_find_badge(manager, "Urban"), qapp)
        _click(_find_badge(manager, "Urban"), qapp)

        assert manager.get_excluded_tag_ids() == []
        assert manager.get_selected_tag_ids() == []

    def test_right_click_on_included_moves_it_to_excluded(
        self, db, tagged_library, qapp
    ):
        manager = TagManager(db, allow_manage=False)
        manager.show()
        qapp.processEvents()

        _click(_find_badge(manager, "Combat"), qapp)
        _right_click(_find_badge(manager, "Combat"), qapp)

        assert manager.get_selected_tag_ids() == []
        assert manager.get_excluded_tag_ids() == [tagged_library["combat"].id]

    def test_excluded_badge_is_grayed_with_strikethrough(
        self, db, tagged_library, qapp
    ):
        manager = TagManager(db, allow_manage=False)
        manager.show()
        qapp.processEvents()

        _right_click(_find_badge(manager, "Urban"), qapp)

        style = _find_badge(manager, "Urban").label.styleSheet()
        assert "line-through" in style

    def test_clear_filter_resets_exclusions(self, db, tagged_library, qapp):
        manager = TagManager(db, allow_manage=False)
        manager.show()
        qapp.processEvents()

        _click(_find_badge(manager, "Combat"), qapp)
        _right_click(_find_badge(manager, "Urban"), qapp)
        manager.clear_filter()

        assert manager.get_selected_tag_ids() == []
        assert manager.get_excluded_tag_ids() == []
        assert manager.has_active_filter() is False

    def test_no_tag_is_mutually_exclusive_with_real_included_tags(
        self, db, tagged_library, qapp
    ):
        manager = TagManager(db, allow_manage=False)
        manager.show()
        qapp.processEvents()

        _click(_find_badge(manager, "Combat"), qapp)
        _click(_find_badge(manager, "No Tag"), qapp)
        assert manager.get_selected_tag_ids() == [NO_TAG_ID]

        _click(_find_badge(manager, "Urban"), qapp)
        assert manager.get_selected_tag_ids() == [tagged_library["urban"].id]

    def test_manage_mode_right_click_opens_menu_not_direct_exclusion(
        self, db, tagged_library, qapp
    ):
        # In the library the badge right-click belongs to the manage menu;
        # exclusion is offered as a menu action there instead.
        manager = TagManager(db, allow_manage=True)
        manager.show()
        qapp.processEvents()

        badge = _find_badge(manager, "Urban")
        badge.right_clicked.emit(badge.tag)
        assert manager.get_excluded_tag_ids() == []

        menu = MagicMock()
        actions = []
        menu.addAction.side_effect = lambda text: (
            actions.append((text, MagicMock())) or actions[-1][1]
        )
        with patch("app.library.tag_manager.QMenu", return_value=menu):
            manager._show_tag_menu(badge.tag, badge, QPoint(0, 0))

        labels = [text for text, _ in actions]
        assert labels[0] == "Exclude from filter"
        exclude_action = actions[0][1]
        exclude_action.triggered.connect.call_args[0][0]()
        assert manager.get_excluded_tag_ids() == [tagged_library["urban"].id]

        # Once excluded, the menu offers to clear the exclusion instead.
        actions.clear()
        with patch("app.library.tag_manager.QMenu", return_value=menu):
            manager._show_tag_menu(badge.tag, badge, QPoint(0, 0))
        assert [text for text, _ in actions][0] == "Clear exclusion"
        actions[0][1].triggered.connect.call_args[0][0]()
        assert manager.get_excluded_tag_ids() == []


class TestDialogTagFiltering:
    """AND + NOT semantics end-to-end through AudioFileSearchDialog."""

    def _visible_titles(self, dialog):
        return {
            item.file.title
            for item in dialog.findChildren(FileSelectItem)
            if not item.isHidden()
        }

    def test_two_included_tags_require_both(self, db, tagged_library, qapp):
        dialog = AudioFileSearchDialog(db, audio_engine=None)
        dialog.show()
        qapp.processEvents()

        _click(_find_badge(dialog.tag_manager, "Combat"), qapp)
        _click(_find_badge(dialog.tag_manager, "Urban"), qapp)

        assert self._visible_titles(dialog) == {"Both"}

    def test_right_click_excludes_files_with_that_tag(self, db, tagged_library, qapp):
        dialog = AudioFileSearchDialog(db, audio_engine=None)
        dialog.show()
        qapp.processEvents()

        _right_click(_find_badge(dialog.tag_manager, "Urban"), qapp)

        assert self._visible_titles(dialog) == {"Combat Only"}

    def test_include_plus_exclude(self, db, tagged_library, qapp):
        dialog = AudioFileSearchDialog(db, audio_engine=None)
        dialog.show()
        qapp.processEvents()

        _click(_find_badge(dialog.tag_manager, "Combat"), qapp)
        _right_click(_find_badge(dialog.tag_manager, "Urban"), qapp)

        assert self._visible_titles(dialog) == {"Combat Only"}
