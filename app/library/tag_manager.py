"""Tag management widget"""

from typing import Optional, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMenu, QLayout, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt, QRect, QSize, QPoint, QTimer

from ..database import DatabaseConnection, Tag
from ..shared.layouts import clear_layout
from ..shared.styles import Styles
from ..shared.icons import IconLibrary
from ..shared.dialogs import TagEditDialog

NO_TAG_ID = -1


class TagBadge(QWidget):
    """A clickable tag badge"""

    clicked = pyqtSignal(Tag)
    remove_clicked = pyqtSignal(Tag)

    def __init__(self, tag: Tag, removable: bool = False, parent=None):
        super().__init__(parent)
        self.tag = tag
        self.removable = removable
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tag label
        color = self.tag.color or Styles.TAG_COLORS[0]
        self.label = QLabel(self.tag.name)
        self.label.setStyleSheet(Styles.tag_badge_style(color))
        self.label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.label)

        if self.removable:
            # Remove button
            remove_btn = QPushButton("×")
            remove_btn.setFixedSize(16, 16)
            remove_btn.setStyleSheet(Styles.tag_remove_button_style(color))
            remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self.tag))
            layout.addWidget(remove_btn)

        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.tag)

    def set_label_style(self, style: str) -> None:
        """Override the tag label style"""
        self.label.setStyleSheet(style)


class FlowLayout(QLayout):
    """Flow layout that wraps widgets based on available width."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 0):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            if widget and widget.isHidden():
                continue
            space_x = self.spacing()
            space_y = self.spacing()
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + bottom


class TagManager(QWidget):
    """Widget for managing tags and filtering by tags"""

    tag_filter_changed = pyqtSignal(list)  # List of selected tag IDs
    tags_modified = pyqtSignal()  # Emitted when tags are created/deleted

    def __init__(
        self,
        db: DatabaseConnection,
        allow_manage: bool = True,
        header_text: str = "Tags",
        parent=None,
    ):
        super().__init__(parent)
        self.db = db
        self._allow_manage = allow_manage
        self._header_text = header_text
        self._selected_tag_ids: set[int] = set()
        self._icons = IconLibrary()
        self._tags_scroll: Optional[QScrollArea] = None

        self._setup_ui()
        self.refresh_tags()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Header with add button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 0, 4, 0)
        header_label = QLabel(self._header_text)
        header_label.setStyleSheet(Styles.title_style(size=14))
        header_layout.addWidget(header_label)

        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Clear tag filter")
        clear_btn.clicked.connect(self.clear_filter)
        header_layout.addWidget(clear_btn)

        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Scrollable tag area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(120)
        self._tags_scroll = scroll

        self.tags_container = QWidget()
        self.tags_container.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.tags_layout = FlowLayout(self.tags_container, margin=0, spacing=8)

        scroll.setWidget(self.tags_container)
        layout.addWidget(scroll)

        if self._allow_manage:
            footer_layout = QHBoxLayout()
            add_btn = QPushButton()
            add_btn.setFixedSize(24, 24)
            add_btn.setIcon(self._icons.icon("plus"))
            add_btn.setIconSize(add_btn.size())
            add_btn.setToolTip("Create new tag")
            add_btn.setStyleSheet(Styles.compact_icon_button_style())
            add_btn.clicked.connect(self._create_tag)
            footer_layout.addWidget(add_btn)
            footer_layout.addStretch()
            layout.addLayout(footer_layout)

    def refresh_tags(self):
        """Reload tags from database"""
        self.tags_container.setUpdatesEnabled(False)
        clear_layout(self.tags_layout)

        # Add "No Tag" pseudo tag first
        no_tag = Tag(id=NO_TAG_ID, name="No Tag", color="#FFFFFF")
        no_tag_badge = TagBadge(no_tag, removable=False)
        no_tag_badge.clicked.connect(self._toggle_tag_filter)
        no_tag_selected = no_tag.id in self._selected_tag_ids
        border_color = Styles.PRIMARY if no_tag_selected else Styles.BORDER
        no_tag_badge.set_label_style(f"""
            background-color: #FFFFFF;
            color: #222;
            border: 1px solid {border_color};
            padding: 3px 10px;
            border-radius: 11px;
            min-height: 18px;
            font-size: 11px;
            font-weight: 700;
        """)
        self.tags_layout.addWidget(no_tag_badge)

        # Add tag badges
        tags = self.db.get_all_tags()
        for tag in tags:
            badge = TagBadge(tag, removable=False)
            badge.clicked.connect(self._toggle_tag_filter)
            if self._allow_manage:
                badge.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                badge.customContextMenuRequested.connect(
                    lambda pos, t=tag, b=badge: self._show_tag_menu(t, b, pos)
                )

            # Highlight if selected
            if tag.id in self._selected_tag_ids:
                badge.set_label_style(
                    Styles.tag_badge_style(tag.color or Styles.TAG_COLORS[0], Styles.PRIMARY)
                )

            self.tags_layout.addWidget(badge)

        self.tags_container.setUpdatesEnabled(True)
        self._update_tag_container_height()
        QTimer.singleShot(0, self._update_tag_container_height)

    def _toggle_tag_filter(self, tag: Tag):
        """Toggle tag in filter selection"""
        if tag.id in self._selected_tag_ids:
            self._selected_tag_ids.remove(tag.id)
        else:
            self._selected_tag_ids.add(tag.id)

        self.refresh_tags()
        self.tag_filter_changed.emit(list(self._selected_tag_ids))
        self._update_tag_container_height()

    def _create_tag(self):
        """Create a new tag"""
        dialog = TagEditDialog(self, title="Create Tag")

        if dialog.exec():
            name = dialog.get_tag_name()
            if name:
                existing = self.db.get_tag_by_name(name)
                if existing:
                    return

                tag = Tag(name=name, color=dialog.get_selected_color())
                self.db.add_tag(tag)
                self.refresh_tags()
                self.tags_modified.emit()
                self._update_tag_container_height()

    def _show_tag_menu(self, tag: Tag, badge: TagBadge, pos):
        """Show context menu for tag"""
        menu = QMenu(self)

        edit_action = menu.addAction("Edit")
        edit_action.triggered.connect(lambda: self._edit_tag(tag))

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_tag(tag))

        menu.exec(badge.mapToGlobal(pos))

    def _edit_tag(self, tag: Tag):
        """Edit a tag"""
        dialog = TagEditDialog(
            self,
            title="Edit Tag",
            name=tag.name,
            color=tag.color
        )

        if dialog.exec():
            name = dialog.get_tag_name()
            color = dialog.get_selected_color()
            if name and (name != tag.name or color != tag.color):
                tag.name = name
                tag.color = color
                self.db.update_tag(tag)
                self.refresh_tags()
                self.tags_modified.emit()
                self._update_tag_container_height()

    def _delete_tag(self, tag: Tag):
        """Delete a tag"""
        self.db.delete_tag(tag.id)
        self._selected_tag_ids.discard(tag.id)
        self.refresh_tags()
        self.tags_modified.emit()
        self._update_tag_container_height()

    def clear_filter(self):
        """Clear tag filter selection"""
        self._selected_tag_ids.clear()
        self.refresh_tags()
        self.tag_filter_changed.emit([])
        self._update_tag_container_height()

    def get_selected_tag_ids(self) -> list[int]:
        """Get currently selected tag IDs"""
        return list(self._selected_tag_ids)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_tag_container_height()

    def _update_tag_container_height(self) -> None:
        if not self._tags_scroll:
            return
        width = self._tags_scroll.viewport().width()
        if width <= 0:
            return
        height = self._calculate_tag_container_height(width)
        if height <= 0:
            return
        self.tags_container.setFixedHeight(height)
        self.tags_container.updateGeometry()

    def _calculate_tag_container_height(self, width: int) -> int:
        margins = self.tags_layout.contentsMargins()
        available_width = max(width - margins.left() - margins.right(), 1)
        x = 0
        y = 0
        line_height = 0
        spacing = self.tags_layout.spacing()

        for index in range(self.tags_layout.count()):
            item = self.tags_layout.itemAt(index)
            if item is None:
                continue

            widget = item.widget()
            if widget and widget.isHidden():
                continue

            item_size = item.sizeHint()
            item_width = item_size.width()
            item_height = item_size.height()

            if x > 0 and (x + item_width) > available_width:
                x = 0
                y += line_height + spacing
                line_height = 0

            x += item_width + spacing
            line_height = max(line_height, item_height)

        if line_height == 0:
            return margins.top() + margins.bottom()

        return y + line_height + margins.top() + margins.bottom()


class TagAssigner(QWidget):
    """Widget for assigning tags to audio files"""

    tags_changed = pyqtSignal()

    def __init__(self, db: DatabaseConnection, audio_file_id: int, parent=None):
        super().__init__(parent)
        self.db = db
        self.audio_file_id = audio_file_id
        self._icons = IconLibrary()
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Show current tags
        self.refresh_tags()

        # Add tag button
        add_btn = QPushButton()
        add_btn.setFixedSize(20, 20)
        add_btn.setIcon(self._icons.icon("plus"))
        add_btn.setIconSize(add_btn.size())
        add_btn.setToolTip("Add tag")
        add_btn.clicked.connect(self._show_add_menu)
        layout.addWidget(add_btn)
        layout.addStretch()

    def refresh_tags(self):
        """Refresh displayed tags"""
        layout = self.layout()
        clear_layout(layout, keep_trailing_items=2)

        # Add current tags
        tags = self.db.get_tags_for_audio_file(self.audio_file_id)
        for i, tag in enumerate(tags):
            badge = TagBadge(tag, removable=True)
            badge.remove_clicked.connect(self._remove_tag)
            layout.insertWidget(i, badge)

    def _show_add_menu(self):
        """Show menu to add a tag"""
        menu = QMenu(self)

        all_tags = self.db.get_all_tags()
        current_tags = self.db.get_tags_for_audio_file(self.audio_file_id)
        current_ids = {t.id for t in current_tags}

        create_action = menu.addAction("Create new tag…")
        create_action.triggered.connect(self._create_and_add_tag)
        if all_tags:
            menu.addSeparator()

        for tag in all_tags:
            if tag.id not in current_ids:
                action = menu.addAction(tag.name)
                action.triggered.connect(lambda checked, t=tag: self._add_tag(t))

        if menu.isEmpty():
            menu.addAction("No more tags available").setEnabled(False)

        # Show at button position
        btn = self.sender()
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _add_tag(self, tag: Tag):
        """Add a tag to the audio file"""
        self.db.add_tag_to_audio_file(self.audio_file_id, tag.id)
        self.refresh_tags()
        self.tags_changed.emit()

    def _remove_tag(self, tag: Tag):
        """Remove a tag from the audio file"""
        self.db.remove_tag_from_audio_file(self.audio_file_id, tag.id)
        self.refresh_tags()
        self.tags_changed.emit()

    def _create_and_add_tag(self):
        """Create a new tag and assign it to this audio file"""
        dialog = TagEditDialog(self, title="Create Tag")
        if not dialog.exec():
            return

        name = dialog.get_tag_name()
        if not name:
            return

        existing = self.db.get_tag_by_name(name)
        if existing:
            self.db.add_tag_to_audio_file(self.audio_file_id, existing.id)
        else:
            tag = Tag(name=name, color=dialog.get_selected_color())
            self.db.add_tag(tag)
            created = self.db.get_tag_by_name(name)
            if created:
                self.db.add_tag_to_audio_file(self.audio_file_id, created.id)

        self.refresh_tags()
        self.tags_changed.emit()
