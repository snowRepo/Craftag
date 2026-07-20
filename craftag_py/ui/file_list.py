"""
file_list.py — Left sidebar panel.

Header layout (2 rows):
  Row 1: [Queue (N)]  [♫ icon]  [📁 icon]  [🗑 clear icon]
  Row 2: [Save All — text, accent]
  ──────────────────────────────────────────────────────────────
  file list / drop hint
"""
from __future__ import annotations
from typing import List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QAbstractItemView, QApplication, QStackedWidget,
    QToolButton, QMessageBox, QLineEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShortcut, QKeySequence

from craftag_py.core.tag_io import AudioTag
class FileItemWidget(QWidget):
    remove_clicked = Signal(str)

    def __init__(self, tag: AudioTag, parent=None):
        super().__init__(parent)
        self.path = tag.path
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(8)

        # Text
        v = QVBoxLayout()
        v.setSpacing(2)
        
        # Title + Badge
        title_row = QHBoxLayout()
        title_row.setSpacing(5)
        
        title = tag.title or tag.filename
        if tag.is_dirty: title = f"● {title}"
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("itemTitleLbl")
        self.lbl_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_row.addWidget(self.lbl_title)
        
        ext = tag.path.rsplit(".", 1)[-1].upper()
        if ext == "WV": ext = "WAVPACK"
        self.lbl_format = QLabel(ext)
        self.lbl_format.setObjectName("formatBadge")
        title_row.addWidget(self.lbl_format)
        title_row.addStretch()
        
        self.lbl_artist = QLabel(tag.artist or "Unknown Artist")
        self.lbl_artist.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_artist.setObjectName("itemArtistLbl")

        v.addLayout(title_row)
        v.addWidget(self.lbl_artist)
        layout.addLayout(v, stretch=1)

        # Remove btn
        self.btn = QToolButton()
        self.btn.setText("✕")
        self.btn.setObjectName("itemRemoveBtn")
        self.btn.setFixedSize(22, 22)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setToolTip("Remove file")
        self.btn.clicked.connect(self._on_remove_clicked)
        layout.addWidget(self.btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

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
                color: #ffffff;
                background: rgba(255, 255, 255, 0.15);
                border-radius: 4px;
            }
            QLabel#formatBadge {
                background-color: rgba(140, 140, 150, 0.25);
                color: #888888;
                border-radius: 5px;
                padding: 1px 4px;
                font-size: 9px;
                font-weight: 700;
                margin-top: 1px;
            }
        """)

    def _on_remove_clicked(self, *args):
        self.remove_clicked.emit(self.path)

    def update_text(self, tag: AudioTag):
        title = tag.title or tag.filename
        if tag.is_dirty:
            title = f"● {title}"
        self.lbl_title.setText(title)
        self.lbl_artist.setText(tag.artist or "Unknown Artist")


class FileListPanel(QWidget):
    """Sidebar showing queued files; emits selection signals."""

    status_message = Signal(str, bool)  # text, is_error
    single_selected = Signal(object)   # AudioTag
    batch_selected = Signal(list)     # List[AudioTag]
    selection_cleared = Signal()

    open_files_requested = Signal()
    open_folder_requested = Signal()
    save_all_requested = Signal()
    clear_requested = Signal()
    theme_toggle_requested = Signal()    # kept for compat, unused

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags: List[AudioTag] = []
        self._dark = False
        self._build_ui()
        self._update_ui()

    def set_dark(self, dark: bool):
        """Called by MainWindow to sync theme state (no toggle button needed)."""
        self._dark = dark

    def set_saving(self, saving: bool):
        """Disable/re-enable the Save All button while a background save runs."""
        self._btn_save_all.setEnabled(not saving and len(self._tags) > 0)
        self._btn_save_all.setText("Saving…" if saving else "Save All")

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

        # Row 1: label + icon buttons + Save All (all on same line)
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self._count_label = QLabel("Queue (0)")
        self._count_label.setObjectName("queueLabel")
        row1.addWidget(self._count_label)
        row1.addStretch()

        # ♫ open files
        self._btn_open = QPushButton("♫")
        self._btn_open.setToolTip("Open audio files  (⌘O)")
        self._btn_open.setFixedSize(28, 28)
        self._btn_open.setObjectName("iconBtn")
        self._btn_open.clicked.connect(self.open_files_requested)
        row1.addWidget(self._btn_open)
        # 📂 open folder (Using standard Emoji/Text glyph for flawless rendering)
        self._btn_folder = QPushButton("📂")
        self._btn_folder.setFixedSize(28, 28)
        self._btn_folder.setObjectName("iconBtn")
        self._btn_folder.clicked.connect(self.open_folder_requested)
        self._btn_folder.setToolTip("Open folder  (⌘⇧O)")
        row1.addWidget(self._btn_folder)

        # 🗑 clear queue (Using crisp native text trash can)
        self._btn_clear = QPushButton("🗑")
        self._btn_clear.setFixedSize(28, 28)
        self._btn_clear.setObjectName("iconBtn")
        self._btn_clear.setEnabled(False)
        self._btn_clear.clicked.connect(self._clear_all)
        self._btn_clear.setToolTip("Clear queue")
        row1.addWidget(self._btn_clear)

        # Save All — accent button, inline with icons
        self._btn_save_all = QPushButton("Save All")
        self._btn_save_all.setObjectName("sidebarSaveBtn")
        self._btn_save_all.setFixedHeight(28)
        self._btn_save_all.setEnabled(False)
        self._btn_save_all.clicked.connect(self._on_save_all_clicked)
        row1.addWidget(self._btn_save_all)

        hv.addLayout(row1)

        # Row 3: Search box
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search files...")
        self._search_box.setFixedHeight(24)
        self._search_box.textChanged.connect(self._filter_list)
        # Prevent stealing shortcuts like Ctrl+A when not active
        self._search_box.setClearButtonEnabled(True)
        hv.addWidget(self._search_box)

        layout.addWidget(header)

        # ── Stack for List vs Hint ──────────────────────────────────────────
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, stretch=1)

        # Page 0: File list
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setAlternatingRowColors(False)
        self._list.setSpacing(1)
        self._list.setObjectName("fileList")
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.setAcceptDrops(True)
        self._stack.addWidget(self._list)

        QShortcut(
            QKeySequence(
                Qt.Key.Key_Delete),
            self._list).activated.connect(
            self._remove_selected)
        QShortcut(
            QKeySequence(
                Qt.Key.Key_Backspace),
            self._list).activated.connect(
            self._remove_selected)
        QShortcut(
            QKeySequence.StandardKey.SelectAll,
            self._list).activated.connect(
            self._list.selectAll)

        # Page 1: Empty state (hint at the base)
        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.addStretch()
        self._hint = QLabel("Drop files or folders here")
        self._hint.setObjectName("dropHint")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._hint)
        self._stack.addWidget(empty_page)

    # ── Public API ──────────────────────────────────────────────────────────

    def add_tags(self, tags: List[AudioTag]):
        existing = {t.path for t in self._tags}
        for tag in tags:
            if tag.path not in existing:
                self._tags.append(tag)
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, tag.path)
                item.setToolTip(tag.path)

                # Assign size hint directly from the widget's layout so it
                # calculates perfectly
                widget = FileItemWidget(tag)
                widget.remove_clicked.connect(self._remove_path)

                item.setSizeHint(widget.sizeHint())

                self._list.addItem(item)
                self._list.setItemWidget(item, widget)
                existing.add(tag.path)
        self._update_ui()

    def update_items(self):
        """Redraw all items (e.g. after selection dirties them)."""
        for tag in self._tags:
            self.refresh_item(tag)
        self._update_ui()

    def get_tag_by_path(self, path: str) -> AudioTag | None:
        for t in self._tags:
            if t.path == path:
                return t
        return None

    def refresh_item(self, tag: AudioTag):
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == tag.path:
                w = self._list.itemWidget(item)
                if isinstance(w, FileItemWidget):
                    w.update_text(tag)
                break

    def all_tags(self) -> List[AudioTag]:
        return list(self._tags)

    def _on_save_all_clicked(self):
        """Wrapper invoked by the Save All button; emits the parameterless signal."""
        self.save_all_requested.emit()

    def on_tags_renamed(self, renamed: list):
        # renamed is list of (old_path, tag)
        paths_map = {old: tag for old, tag in renamed}
        for i in range(self._list.count()):
            item = self._list.item(i)
            old_path = item.data(Qt.ItemDataRole.UserRole)
            if old_path in paths_map:
                tag = paths_map[old_path]
                item.setData(Qt.ItemDataRole.UserRole, tag.path)
                item.setToolTip(tag.path)
                w = self._list.itemWidget(item)
                if isinstance(w, FileItemWidget):
                    w.path = tag.path
        self.update_items()

    # ── Internal ────────────────────────────────────────────────────────────

    def _filter_list(self, query: str):
        q = query.lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            tag_path = item.data(Qt.ItemDataRole.UserRole)
            if not q:
                item.setHidden(False)
            else:
                tag = self.get_tag_by_path(tag_path)
                if not tag: continue
                match = (
                    q in (tag.title or "").lower() or
                    q in (tag.artist or "").lower() or
                    q in tag.filename.lower()
                )
                item.setHidden(not match)

    def _on_selection_changed(self):
        paths = [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
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

        paths_to_remove = {item.data(Qt.ItemDataRole.UserRole) for item in selected_items}
        
        # Check if any selected items are dirty
        tags_to_remove = [t for t in self._tags if t.path in paths_to_remove]
        if any(t.is_dirty for t in tags_to_remove):
            reply = QMessageBox.warning(
                self, "Unsaved Changes",
                "Some selected files have unsaved changes.\nAre you sure you want to remove them from the queue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._tags = [t for t in self._tags if t.path not in paths_to_remove]

        for item in selected_items:
            row = self._list.row(item)
            self._list.takeItem(row)

        self._update_ui()
        self.status_message.emit(
            f"Removed {len(selected_items)} file(s).", False)
        self._on_selection_changed()

    def _remove_path(self, path: str):
        # Called when the inline × button is clicked
        tag = self.get_tag_by_path(path)
        if tag and tag.is_dirty:
            reply = QMessageBox.warning(
                self, "Unsaved Changes",
                f"'{tag.title or tag.filename}' has unsaved changes.\nAre you sure you want to remove it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._tags = [t for t in self._tags if t.path != path]
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                self._list.takeItem(i)
                break
        self._update_ui()
        self.status_message.emit("Removed 1 file.", False)
        self._on_selection_changed()

    def _clear_all(self):
        if any(t.is_dirty for t in self._tags):
            reply = QMessageBox.warning(
                self, "Unsaved Changes",
                "There are files with unsaved changes in the queue.\nAre you sure you want to clear the entire queue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

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

