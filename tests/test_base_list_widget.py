"""Tests for BaseListWidget.select_relative — the keyboard next/prev navigation
primitive used by the Ctrl+Left / Ctrl+Right shortcuts.

Exercised through a minimal concrete subclass so the navigation logic is tested
without a database or a specific entity type.
"""

from types import SimpleNamespace

import pytest

from app.shared.base_list_widget import BaseListWidget


class _FakeList(BaseListWidget):
    _entity_name = "Thing"
    _display_attr = "name"

    def __init__(self, items):
        self._seed = items
        self.selected: list[int] = []
        super().__init__(db=None)

    def _get_all_items(self):
        return list(self._seed)

    def _search_items(self, query):
        return list(self._seed)

    def _get_item_by_id(self, item_id):
        return next((x for x in self._seed if x.id == item_id), None)

    def _emit_selected(self, item):
        self.selected.append(item.id)


def _items(n):
    return [SimpleNamespace(id=i + 1, name=f"Item {i + 1}") for i in range(n)]


@pytest.fixture
def listw(qapp):
    return _FakeList(_items(3))  # ids 1, 2, 3


class TestSelectRelative:
    def test_forward_from_nothing_selects_first(self, listw):
        assert listw.get_selected_id() is None
        assert listw.select_relative(1) == 1
        assert listw.selected[-1] == 1

    def test_backward_from_nothing_selects_last(self, listw):
        assert listw.select_relative(-1) == 3

    def test_steps_forward(self, listw):
        listw.select_relative(1)  # -> 1
        assert listw.select_relative(1) == 2
        assert listw.select_relative(1) == 3

    def test_steps_backward(self, listw):
        listw.select_by_id(3)
        assert listw.select_relative(-1) == 2

    def test_no_wrap_at_end(self, listw):
        listw.select_by_id(3)
        assert listw.select_relative(1) is None
        assert listw.get_selected_id() == 3  # selection unchanged

    def test_no_wrap_at_start(self, listw):
        listw.select_by_id(1)
        assert listw.select_relative(-1) is None
        assert listw.get_selected_id() == 1

    def test_empty_list_returns_none(self, qapp):
        assert _FakeList([]).select_relative(1) is None

    def test_emits_selection_on_move(self, listw):
        listw.select_by_id(1)
        listw.selected.clear()
        listw.select_relative(1)
        assert listw.selected == [2]


class TestFocusList:
    def test_selects_first_when_nothing_selected(self, listw):
        assert listw.get_selected_id() is None
        listw.focus_list()
        assert listw.get_selected_id() == 1

    def test_keeps_existing_selection(self, listw):
        listw.select_by_id(2)
        listw.focus_list()
        assert listw.get_selected_id() == 2

    def test_empty_list_does_not_crash(self, qapp):
        empty = _FakeList([])
        empty.focus_list()  # must not raise
        assert empty.get_selected_id() is None
