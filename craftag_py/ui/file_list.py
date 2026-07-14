"""
file_list.py — Left sidebar panel.

Header layout (2 rows):
  Row 1: [Queue (N)]  [♫ icon]  [📁 icon]  [☀/🌙 theme toggle]
  Row 2: [Clear All — text]              [Save All — text, accent]
  ──────────────────────────────────────────────────────────────
  file list / drop hint
"""
from __future__ import annotations
from typing import List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QAbstractItemView, QApplication, QStackedWidget,
    QToolButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import QStyle

from craftag_py.core.tag_io import AudioTag


class FileItemWidget(QWidget):
    remove_clicked = Signal(str)

    def __init__(self, tag: AudioTag, parent=None):
        super().__init__(parent)
        self.path = tag.path
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(8)

        # Text
        v = QVBoxLayout()
        v.setSpacing(2)
        self.lbl_title = QLabel(tag.title or tag.filename)
        self.lbl_title.setObjectName("itemTitleLbl")
        self.lbl_title.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lbl_artist = QLabel(tag.artist or "Unknown Artist")
        self.lbl_artist.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lbl_artist.setObjectName("itemArtistLbl")
        
        v.addWidget(self.lbl_title)
        v.addWidget(self.lbl_artist)
        layout.addLayout(v, stretch=1)

        # Remove btn
        self.btn = QToolButton()
        self.btn.setText("✕")
        self.btn.setObjectName("itemRemoveBtn")
        self.btn.setFixedSize(22, 22)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setToolTip("Remove file")
        self.btn.clicked.connect(self._on_remove_clicked)
        layout.addWidget(self.btn, alignment=Qt.AlignRight | Qt.AlignVCenter)

        # Ensure widgets don't get the global editor background
        self.setStyleSheet("""
            QWidget { background: transparent; border: none; }
            QLabel#itemArtistLbl { color: #888888; border: none; }
            QToolButton#itemRemoveBtn {
                background: transparent;
                color: #888888;
                border: none;
                font-size: 14px;
                font-weight: bold;
            }
            QToolButton#itemRemoveBtn:hover {
                color: #ff4a4a;
                background: rgba(255, 74, 74, 0.15);
                border-radius: 4px;
            }
        """)

    def _on_remove_clicked(self, *args):
        self.remove_clicked.emit(self.path)

    def update_text(self, tag: AudioTag):
        self.lbl_title.setText(tag.title or tag.filename)
        self.lbl_artist.setText(tag.artist or "Unknown Artist")

class FileListPanel(QWidget):
    """Sidebar showing queued files; emits selection signals."""

    status_message    = Signal(str, bool) # text, is_error
    single_selected   = Signal(object)   # AudioTag
    batch_selected    = Signal(list)     # List[AudioTag]
    selection_cleared = Signal()

    open_files_requested  = Signal()
    open_folder_requested = Signal()
    save_all_requested    = Signal()
    clear_requested       = Signal()
    theme_toggle_requested = Signal()    # light ↔ dark

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags: List[AudioTag] = []
        self._dark = True
        self._build_ui()
        self._update_ui()

    def set_dark(self, dark: bool):
        """Called by MainWindow to update the toggle icon."""
        self._dark = dark
        self._btn_theme.setText("☀" if dark else "◑")
        self._btn_theme.setToolTip("Switch to light mode" if dark else "Switch to dark mode")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header widget ───────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("sidebarHeader")
        hv = QVBoxLayout(header)
        hv.setContentsMargins(10, 6, 8, 6)
        hv.setSpacing(5)

        # Row 1: label + icon buttons
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self._count_label = QLabel("Queue (0)")
        self._count_label.setObjectName("queueLabel")
        row1.addWidget(self._count_label)
        row1.addStretch()

        # ♫ open files — music note icon
        self._btn_open = QPushButton("♫")
        self._btn_open.setToolTip("Open audio files  (⌘O)")
        self._btn_open.setFixedSize(28, 28)
        self._btn_open.setObjectName("iconBtn")
        self._btn_open.clicked.connect(self.open_files_requested)
        row1.addWidget(self._btn_open)

        # 📁 open folder — native folder icon
        self._btn_folder = QPushButton()
        self._btn_folder.setToolTip("Open folder  (⌘⇧O)")
        self._btn_folder.setFixedSize(28, 28)
        self._btn_folder.setObjectName("iconBtn")
        folder_icon = QApplication.style().standardIcon(QStyle.SP_DirIcon)
        self._btn_folder.setIcon(folder_icon)
        self._btn_folder.clicked.connect(self.open_folder_requested)
        row1.addWidget(self._btn_folder)

        # ☀/◑ theme toggle
        self._btn_theme = QPushButton("☀")
        self._btn_theme.setToolTip("Switch to light mode")
        self._btn_theme.setFixedSize(28, 28)
        self._btn_theme.setObjectName("iconBtn")
        self._btn_theme.clicked.connect(self.theme_toggle_requested)
        row1.addWidget(self._btn_theme)

        hv.addLayout(row1)

        # Row 2: Clear All (text) + Save All (text, accent) — below queue label
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self._btn_clear = QPushButton("Clear All")
        self._btn_clear.setObjectName("sidebarClearBtn")
        self._btn_clear.setFixedHeight(24)
        self._btn_clear.setEnabled(False)
        self._btn_clear.clicked.connect(self._clear_all)
        row2.addWidget(self._btn_clear)

        row2.addStretch()

        self._btn_save_all = QPushButton("Save All")
        self._btn_save_all.setObjectName("sidebarSaveBtn")
        self._btn_save_all.setFixedHeight(24)
        self._btn_save_all.setEnabled(False)
        self._btn_save_all.clicked.connect(self.save_all_requested)
        row2.addWidget(self._btn_save_all)

        hv.addLayout(row2)

        layout.addWidget(header)

        # ── Stack for List vs Hint ──────────────────────────────────────────
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, stretch=1)

        # Page 0: File list
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.setAlternatingRowColors(False)
        self._list.setSpacing(1)
        self._list.setObjectName("fileList")
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.setAcceptDrops(True)
        self._stack.addWidget(self._list)

        QShortcut(QKeySequence(Qt.Key_Delete), self._list).activated.connect(self._remove_selected)
        QShortcut(QKeySequence(Qt.Key_Backspace), self._list).activated.connect(self._remove_selected)

        # Page 1: Empty state (hint at the base)
        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.addStretch()
        self._hint = QLabel("Drop files or folders here")
        self._hint.setObjectName("dropHint")
        self._hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self._hint)
        self._stack.addWidget(empty_page)

    # ── Public API ──────────────────────────────────────────────────────────

    def add_tags(self, tags: List[AudioTag]):
        existing = {t.path for t in self._tags}
        for tag in tags:
            if tag.path not in existing:
                self._tags.append(tag)
                item = QListWidgetItem()
                item.setData(Qt.UserRole, tag.path)
                item.setToolTip(tag.path)
                
                # Assign size hint directly from the widget's layout so it calculates perfectly
                widget = FileItemWidget(tag)
                widget.remove_clicked.connect(self._remove_path)
                
                item.setSizeHint(widget.sizeHint())
                
                self._list.addItem(item)
                self._list.setItemWidget(item, widget)
                existing.add(tag.path)
        self._update_ui()

    def get_tag_by_path(self, path: str) -> AudioTag | None:
        for t in self._tags:
            if t.path == path:
                return t
        return None

    def refresh_item(self, tag: AudioTag):
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.UserRole) == tag.path:
                w = self._list.itemWidget(item)
                if isinstance(w, FileItemWidget):
                    w.update_text(tag)
                break

    def all_tags(self) -> List[AudioTag]:
        return list(self._tags)

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_selection_changed(self):
        paths = [
            self._list.item(i).data(Qt.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).isSelected()
        ]
        if not paths:
            self.selection_cleared.emit()
            return
        tags = [t for t in self._tags if t.path in set(paths)]
        if len(tags) == 1:
            self.single_selected.emit(tags[0])
        elif len(tags) > 1:
            self.batch_selected.emit(tags)

    def _remove_selected(self):
        selected_items = self._list.selectedItems()
        if not selected_items:
            return
            
        paths_to_remove = {item.data(Qt.UserRole) for item in selected_items}
        self._tags = [t for t in self._tags if t.path not in paths_to_remove]
        
        for item in selected_items:
            row = self._list.row(item)
            self._list.takeItem(row)
            
        self._update_ui()
        self.status_message.emit(f"Removed {len(selected_items)} file(s).", False)
        self._on_selection_changed()

    def _remove_path(self, path: str):
        # Called when the inline × button is clicked
        self._tags = [t for t in self._tags if t.path != path]
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.UserRole) == path:
                self._list.takeItem(i)
                break
        self._update_ui()
        self.status_message.emit("Removed 1 file.", False)
        self._on_selection_changed()

    def _clear_all(self):
        self._tags.clear()
        self._list.clear()
        self.selection_cleared.emit()
        self.clear_requested.emit()
        self._update_ui()
        self.status_message.emit("Queue cleared.", False)

    def _update_ui(self):
        n = len(self._tags)
        self._count_label.setText(f"Queue ({n})")
        has = n > 0
        self._btn_clear.setEnabled(has)
        self._btn_save_all.setEnabled(has)
        self._stack.setCurrentIndex(0 if has else 1)
