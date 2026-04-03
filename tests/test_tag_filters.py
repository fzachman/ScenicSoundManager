"""Regression tests for tag-based UI filters."""

import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from app.database import AudioFile, DatabaseConnection, Tag
from app.library.tag_manager import TagBadge, TagManager
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
