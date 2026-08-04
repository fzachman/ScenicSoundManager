"""Base list widget for sidebar lists"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..library.search_bar import SearchBar
from .dialogs import TextInputDialog
from .icons import IconLibrary
from .styles import Styles
from .theme import theme_manager


class BaseListWidget(QWidget):
    """Base class for sidebar list widgets (scenes, playlists, etc.)

    Subclasses must set _entity_name and _display_attr as class attributes,
    and implement all methods that raise NotImplementedError.
    """

    _entity_name: str = ""  # e.g. "Scene" or "Playlist"
    _display_attr: str = ""  # attribute for display text, e.g. "title" or "name"

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._items = []
        self._icons = IconLibrary()

        self.setMinimumWidth(200)
        self.setMaximumWidth(300)

        self._setup_ui()
        self._apply_theme_styles()
        theme_manager.theme_changed.connect(self._apply_theme_styles)
        self.refresh()
        self._update_order_button_state()

    def _apply_theme_styles(self):
        """Re-apply palette-dependent styles/icons; re-run on theme change."""
        self._header_label.setStyleSheet(Styles.title_style(size=16))
        # Icons rasterize with a baked color, so re-set on theme change.
        self.order_btn.setIcon(self._icons.icon("list"))
        self.order_btn.setStyleSheet(Styles.compact_icon_button_style())

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 0, 4, 0)
        self._header_label = QLabel(f"{self._entity_name}s")
        header_layout.addWidget(self._header_label)
        header_layout.addStretch()

        # Icon/style applied by _apply_theme_styles.
        self.order_btn = QPushButton()
        self.order_btn.setCheckable(True)
        self.order_btn.setFixedSize(28, 28)
        self.order_btn.setIconSize(self.order_btn.size())
        self.order_btn.setToolTip(f"Unlock {self._entity_name} Order")
        self.order_btn.toggled.connect(self._set_ordering_enabled)
        header_layout.addWidget(self.order_btn)
        layout.addLayout(header_layout)

        # Search bar
        self.search_bar = SearchBar(
            placeholder=f"Search {self._entity_name.lower()}s..."
        )
        self.search_bar.search_changed.connect(self._on_search)
        layout.addWidget(self.search_bar)

        # List widget
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.list_widget.setSpacing(2)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list_widget)

        # New item button
        new_btn = QPushButton(f"+ New {self._entity_name}")
        new_btn.clicked.connect(self._create_item)
        layout.addWidget(new_btn)

    def refresh(self):
        """Reload items from database"""
        query = self.search_bar.get_text()
        if query:
            self._items = self._search_items(query)
        else:
            self._items = self._get_all_items()

        self._update_list()
        self._update_order_button_state()

    def _update_list(self):
        """Update the list widget"""
        current_id = self.get_selected_id()

        self.list_widget.clear()
        for item in self._items:
            display_text = getattr(item, self._display_attr)
            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self.list_widget.addItem(list_item)

            if item.id == current_id:
                list_item.setSelected(True)

    def _on_search(self, query: str):
        self.refresh()
        self._update_order_button_state()

    def _on_item_clicked(self, list_item: QListWidgetItem):
        item_id = list_item.data(Qt.ItemDataRole.UserRole)
        item = self._get_item_by_id(item_id)
        if item:
            self._emit_selected(item)

    def _on_item_double_clicked(self, list_item: QListWidgetItem):
        item_id = list_item.data(Qt.ItemDataRole.UserRole)
        item = self._get_item_by_id(item_id)
        if item:
            self._rename_item(item)

    def _show_context_menu(self, pos):
        list_item = self.list_widget.itemAt(pos)
        if not list_item:
            return

        item_id = list_item.data(Qt.ItemDataRole.UserRole)
        item = self._get_item_by_id(item_id)
        if not item:
            return

        menu = QMenu(self)

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._rename_item(item))

        duplicate_action = menu.addAction("Duplicate")
        duplicate_action.triggered.connect(lambda: self._do_duplicate(item))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_item(item))

        menu.exec(self.list_widget.mapToGlobal(pos))

    def _create_item(self):
        dialog = TextInputDialog(
            self, title=f"New {self._entity_name}", label=f"{self._entity_name} name:"
        )

        if dialog.exec():
            name = dialog.get_text()
            if name:
                item = self._create_new_item(name)
                self.refresh()
                self._emit_created(item)
                self.select_by_id(item.id)

    def _rename_item(self, item):
        current_name = getattr(item, self._display_attr)
        dialog = TextInputDialog(
            self,
            title=f"Rename {self._entity_name}",
            label=f"{self._entity_name} name:",
            default=current_name,
        )

        if dialog.exec():
            name = dialog.get_text()
            if name and name != current_name:
                setattr(item, self._display_attr, name)
                self._update_item(item)
                self.refresh()

    def _do_duplicate(self, item):
        new_item = self._duplicate_item(item)
        self.refresh()
        self._emit_created(new_item)
        self.select_by_id(new_item.id)

    def _delete_item(self, item):
        self._delete_item_by_id(item.id)
        self.refresh()
        self._emit_deleted(item.id)

    def get_selected_id(self) -> int | None:
        items = self.list_widget.selectedItems()
        if items:
            return items[0].data(Qt.ItemDataRole.UserRole)
        return None

    def select_by_id(self, item_id: int):
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            if list_item.data(Qt.ItemDataRole.UserRole) == item_id:
                list_item.setSelected(True)
                item = self._get_item_by_id(item_id)
                if item:
                    self._emit_selected(item)
                break

    def select_relative(self, delta: int) -> int | None:
        """Move the selection by ``delta`` rows in display order and emit it.

        Used by the keyboard shortcuts to step to the next/previous item. Stops
        at the ends (no wrap-around); with nothing selected, ``+1`` lands on the
        first row and ``-1`` on the last. Returns the newly selected id, or
        ``None`` if there was no move (empty list / already at the edge).
        """
        count = self.list_widget.count()
        if count == 0:
            return None

        current_id = self.get_selected_id()
        current_row = -1
        if current_id is not None:
            for i in range(count):
                if (
                    self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                    == current_id
                ):
                    current_row = i
                    break

        if current_row < 0:
            new_row = 0 if delta > 0 else count - 1
        else:
            new_row = current_row + delta
            if new_row < 0 or new_row >= count:
                return None

        list_item = self.list_widget.item(new_row)
        item_id = list_item.data(Qt.ItemDataRole.UserRole)
        self.list_widget.setCurrentItem(list_item)  # single-select: deselects others
        list_item.setSelected(True)
        item = self._get_item_by_id(item_id)
        if item:
            self._emit_selected(item)
        return item_id

    def focus_list(self):
        """Give the list keyboard focus, ensuring a row is selected.

        Called when the tab is shown so the header's order/search controls don't
        hold focus — otherwise the Space shortcut would toggle the focused order
        button instead of play/pause. Selection persists across tab switches; if
        nothing is selected yet (first visit), the first item is selected.
        """
        if self.get_selected_id() is None:
            self.select_relative(1)  # nothing selected -> select the first row
        self.list_widget.setFocus()

    def _set_ordering_enabled(self, enabled: bool):
        lock_text = "Lock" if enabled else "Unlock"
        self.order_btn.setToolTip(f"{lock_text} {self._entity_name} Order")
        self.list_widget.setDragEnabled(enabled)
        self.list_widget.setAcceptDrops(enabled)
        self.list_widget.setDropIndicatorShown(enabled)
        mode = (
            QAbstractItemView.DragDropMode.InternalMove
            if enabled
            else QAbstractItemView.DragDropMode.NoDragDrop
        )
        self.list_widget.setDragDropMode(mode)

    def _on_rows_moved(self, parent, start, end, destination, row):
        if not self.order_btn.isChecked():
            return
        self._persist_order()

    def _persist_order(self):
        ids = []
        item_by_id = {item.id: item for item in self._items}
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            item_id = list_item.data(Qt.ItemDataRole.UserRole)
            ids.append(item_id)
        self._reorder_items(ids)
        self._items = [item_by_id[sid] for sid in ids if sid in item_by_id]

    def _update_order_button_state(self):
        has_query = bool(self.search_bar.get_text())
        if has_query and self.order_btn.isChecked():
            self.order_btn.setChecked(False)
        self.order_btn.setEnabled(not has_query)

    # --- Abstract methods (subclasses must override) ---

    def _get_all_items(self) -> list:
        raise NotImplementedError

    def _search_items(self, query: str) -> list:
        raise NotImplementedError

    def _get_item_by_id(self, item_id: int):
        raise NotImplementedError

    def _create_new_item(self, name: str):
        """Create a new item with the given name, persist it, return with id set."""
        raise NotImplementedError

    def _update_item(self, item):
        raise NotImplementedError

    def _delete_item_by_id(self, item_id: int):
        raise NotImplementedError

    def _duplicate_item(self, item):
        """Duplicate the item, persist it, return the new item with id set."""
        raise NotImplementedError

    def _reorder_items(self, ids: list[int]):
        raise NotImplementedError

    def _emit_selected(self, item):
        raise NotImplementedError

    def _emit_created(self, item):
        raise NotImplementedError

    def _emit_deleted(self, item_id: int):
        raise NotImplementedError
