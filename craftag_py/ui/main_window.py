"""
main_window.py — Craftag main window.
Supports light/dark theme toggle wired through FileListPanel's header.
"""
from __future__ import annotations
import os

from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar, QFileDialog,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent

from craftag_py.core.tag_io import AudioTag, read_tag, read_folder, save_tag
from craftag_py.ui.file_list import FileListPanel
from craftag_py.ui.editor_panel import EditorPanel


# ── Background loader ──────────────────────────────────────────────────────────

class LoadWorker(QObject):
    done     = Signal(list)
    finished = Signal()

    def __init__(self, paths: list[str]):
        super().__init__()
        self._paths = paths

    def run(self):
        results: list[AudioTag] = []
        try:
            for p in self._paths:
                try:
                    if os.path.isdir(p):
                        results.extend(read_folder(p))
                    elif os.path.isfile(p):
                        tag = read_tag(p)
                        if tag:
                            results.append(tag)
                except Exception as e:
                    print(f"[LoadWorker] skipping {p}: {e}")
        finally:
            # Always emit — even on total failure — so UI never hangs
            self.done.emit(results)
            self.finished.emit()


# ── Main Window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Craftag")
        self.setMinimumSize(820, 540)
        self.resize(1060, 660)
        self.setAcceptDrops(True)
        self._dark = True

        icon_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "logo.png"
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._apply_stylesheet()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setObjectName("mainSplitter")

        self._file_list = FileListPanel()
        self._file_list.setMinimumWidth(200)
        self._file_list.setMaximumWidth(300)
        self._file_list.open_files_requested.connect(self._open_files)
        self._file_list.open_folder_requested.connect(self._open_folder)
        self._file_list.save_all_requested.connect(self._save_all)
        self._file_list.single_selected.connect(self._on_single_selected)
        self._file_list.batch_selected.connect(self._on_batch_selected)
        self._file_list.selection_cleared.connect(self._on_selection_cleared)
        self._file_list.theme_toggle_requested.connect(self._toggle_theme)
        self._file_list.status_message.connect(self._show_status)
        splitter.addWidget(self._file_list)

        self._editor = EditorPanel()
        self._editor.status_message.connect(self._show_status)
        self._editor.set_dark(self._dark)   # sync initial theme
        splitter.addWidget(self._editor)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.setCentralWidget(splitter)

        self._status = QStatusBar()
        self._status.setObjectName("statusBar")
        self.setStatusBar(self._status)

    # ── Theme ───────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        self._dark = not self._dark
        self._file_list.set_dark(self._dark)
        self._editor.set_dark(self._dark)
        self._apply_stylesheet()

    def _apply_stylesheet(self):
        dark = self._dark
        if dark:
            BG          = "#0d0f1a"
            SIDEBAR_BG  = "#0b0d18"
            HEADER_BG   = "#0f1120"
            BORDER      = "#1e2030"
            SEP         = "#1e2030"
            TEXT        = "#e0e0e8"
            TEXT_MUTED  = "#6a7090"
            TEXT_SUBTLE = "#383c58"
            INPUT_BG    = "rgba(0,0,0,0.3)"
            INPUT_BOR   = "#1e2235"
            LIST_ITEM   = "#c8ccd8"
            LIST_SEL    = "rgba(10,132,255,0.16)"
            LIST_HOVER  = "rgba(255,255,255,0.04)"
            STATUS_BG   = "#080a14"
            STATUS_BOR  = "#141628"
            HINT_COL    = "#2e3250"
            SCROLL_TH   = "#252840"
            SCROLL_HV   = "#353a58"
            BTN_BG      = "#181a2a"
            BTN_BOR     = "#252840"
            BTN_COL     = "#9098b8"
            BTN_HV_BG   = "#1e2136"
            BTN_HV_BOR  = "#303558"
            BTN_HV_COL  = "#c0c8e0"
        else:
            BG          = "#f5f5f7"
            SIDEBAR_BG  = "#ececee"
            HEADER_BG   = "#e4e4e8"
            BORDER      = "rgba(0,0,0,0.1)"
            SEP         = "rgba(0,0,0,0.1)"
            TEXT        = "#1d1d1f"
            TEXT_MUTED  = "#636366"
            TEXT_SUBTLE = "#aeaeb2"
            INPUT_BG    = "#ffffff"
            INPUT_BOR   = "rgba(0,0,0,0.14)"
            LIST_ITEM   = "#1d1d1f"
            LIST_SEL    = "rgba(0,113,227,0.12)"
            LIST_HOVER  = "rgba(0,0,0,0.04)"
            STATUS_BG   = "#e0e0e4"
            STATUS_BOR  = "rgba(0,0,0,0.1)"
            HINT_COL    = "#aeaeb2"
            SCROLL_TH   = "rgba(0,0,0,0.2)"
            SCROLL_HV   = "rgba(0,0,0,0.35)"
            BTN_BG      = "#ffffff"
            BTN_BOR     = "rgba(0,0,0,0.14)"
            BTN_COL     = "#636366"
            BTN_HV_BG   = "#f0f0f4"
            BTN_HV_BOR  = "rgba(0,0,0,0.22)"
            BTN_HV_COL  = "#1d1d1f"

        ACCENT      = "#0a84ff" if dark else "#0071e3"
        ACCENT_SOFT = "rgba(10,132,255,0.12)" if dark else "rgba(0,113,227,0.10)"
        ACCENT_DARK = "#0060cc"
        DANGER      = "#e05555" if dark else "#d94040"

        self.setStyleSheet(f"""
        /* ── Globals ── */
        QMainWindow {{
            background: {BG};
            color: {TEXT};
            font-family: -apple-system, "SF Pro Text", "Segoe UI", sans-serif;
            font-size: 13px;
        }}

        QSplitter::handle {{ background: {SEP}; width: 1px; }}

        /* ── Sidebar ── */
        FileListPanel {{ background: {SIDEBAR_BG}; }}

        #sidebarHeader {{
            background: {HEADER_BG};
            border-bottom: 1px solid {BORDER};
        }}

        #queueLabel {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: {TEXT_MUTED};
        }}

        /* Small icon buttons (row 1) */
        #iconBtn {{
            background: transparent;
            border: 1px solid {BTN_BOR};
            border-radius: 6px;
            color: {TEXT_MUTED};
            font-size: 13px;
            padding: 0;
        }}
        #iconBtn:hover {{
            background: {ACCENT_SOFT};
            border-color: {ACCENT};
            color: {ACCENT};
        }}
        #iconBtn:pressed {{ background: {ACCENT_SOFT}; }}
        #iconBtn:disabled {{ opacity: 0.3; }}

        /* Text buttons (row 2) */
        #textBtn {{
            background: transparent;
            border: none;
            color: {TEXT_MUTED};
            font-size: 11px;
            padding: 0 4px;
            text-align: left;
        }}
        #textBtn:hover {{ color: {DANGER}; }}
        #textBtn:disabled {{ opacity: 0.3; }}

        #accentTextBtn {{
            background: transparent;
            border: none;
            color: {ACCENT};
            font-size: 11px;
            font-weight: 600;
            padding: 0 4px;
            text-align: right;
        }}
        #accentTextBtn:hover {{ color: {"#2a94ff" if dark else "#0060cc"}; }}
        #accentTextBtn:disabled {{ opacity: 0.3; }}

        /* Clear All — subtle danger button */
        #sidebarClearBtn {{
            background: transparent;
            border: 1px solid {BTN_BOR};
            border-radius: 5px;
            color: {TEXT_MUTED};
            font-size: 11px;
            padding: 0 8px;
        }}
        #sidebarClearBtn:hover {{
            background: {"rgba(224,85,85,0.1)" if dark else "rgba(217,64,64,0.07)"};
            border-color: {DANGER};
            color: {DANGER};
        }}
        #sidebarClearBtn:disabled {{ opacity: 0.3; }}

        /* Save All — accent button */
        #sidebarSaveBtn {{
            background: {ACCENT_SOFT};
            border: 1px solid {ACCENT};
            border-radius: 5px;
            color: {ACCENT};
            font-size: 11px;
            font-weight: 600;
            padding: 0 8px;
        }}
        #sidebarSaveBtn:hover {{
            background: {ACCENT};
            color: #fff;
        }}
        #sidebarSaveBtn:disabled {{ opacity: 0.3; }}

        /* ── File list ── */
        #fileList {{
            background: {SIDEBAR_BG};
            border: none;
            outline: none;
        }}
        #fileList::item {{
            border-bottom: 1px solid {BORDER};
            color: {LIST_ITEM};
        }}
        #fileList::item:selected {{
            background: {LIST_SEL};
            color: {TEXT};
            outline: none;
        }}
        #fileList::item:focus {{
            outline: none;
        }}
        
        #itemTitleLbl {{
            color: {LIST_ITEM};
        }}
        
        #itemArtistLbl {{
            color: {TEXT_MUTED};
        }}
        
        #itemRemoveBtn {{
            background: transparent;
            color: {TEXT_MUTED};
            border: none;
            font-size: 15px;
            font-weight: bold;
            padding-bottom: 2px;
        }}
        #itemRemoveBtn:hover {{
            color: {DANGER};
            background: {"rgba(224,85,85,0.1)" if dark else "rgba(217,64,64,0.07)"};
            border-radius: 4px;
        }}
        #fileList::item:hover:!selected {{ background: {LIST_HOVER}; }}

        #dropHint {{
            color: {TEXT_MUTED};
            font-size: 12px;
            padding: 24px;
        }}

        /* Separator line */
        #hsep {{ background: {SEP}; color: {SEP}; }}

        /* ── Editor ── */
        EditorPanel {{ background: {BG}; }}

        #trackTitle {{
            font-size: 14px;
            font-weight: 600;
            color: {TEXT};
        }}
        #trackArtist {{
            font-size: 12px;
            color: {TEXT_MUTED};
        }}
        #batchNote {{
            font-size: 11px;
            color: {"#c8a040" if dark else "#b07000"};
        }}
        #fieldLabel {{
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: {TEXT_MUTED};
        }}

        /* ── Inputs ── */
        QLineEdit {{
            background: {INPUT_BG};
            border: 1px solid {INPUT_BOR};
            border-radius: 6px;
            color: {TEXT};
            padding: 4px 8px;
            selection-background-color: {ACCENT_SOFT};
        }}
        QLineEdit:focus {{
            border-color: {ACCENT};
            background: {"rgba(10,132,255,0.06)" if dark else "rgba(0,113,227,0.04)"};
        }}
        QLineEdit:disabled {{ color: {TEXT_SUBTLE}; }}

        /* ── Buttons ── */
        QPushButton {{
            background: {BTN_BG};
            border: 1px solid {BTN_BOR};
            border-radius: 6px;
            color: {BTN_COL};
            padding: 4px 12px;
        }}
        QPushButton:hover {{
            background: {BTN_HV_BG};
            border-color: {BTN_HV_BOR};
            color: {BTN_HV_COL};
        }}
        QPushButton:pressed {{ opacity: 0.8; }}
        QPushButton:disabled {{ opacity: 0.35; }}

        QPushButton#primary {{
            background: {ACCENT};
            border-color: {ACCENT};
            color: #fff;
            font-weight: 600;
            padding: 6px 20px;
        }}
        QPushButton#primary:hover {{ background: {"#2a94ff" if dark else "#0077ed"}; }}
        QPushButton#primary:pressed {{ background: {ACCENT_DARK}; }}

        QPushButton#smallBtn {{
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 5px;
        }}
        QPushButton#smallDangerBtn {{
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 5px;
            color: {DANGER};
            border-color: {"rgba(224,85,85,0.3)" if dark else "rgba(217,64,64,0.3)"};
            background: transparent;
        }}
        QPushButton#smallDangerBtn:hover {{
            background: {"rgba(224,85,85,0.1)" if dark else "rgba(217,64,64,0.08)"};
            border-color: {DANGER};
        }}

        /* ── Scrollbar ── */
        QScrollBar:vertical {{
            background: transparent; width: 5px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {SCROLL_TH}; border-radius: 2px; min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {SCROLL_HV}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

        /* ── Status bar ── */
        #statusBar {{
            background: {STATUS_BG};
            border-top: 1px solid {STATUS_BOR};
            font-size: 12px;
            padding: 1px 12px;
        }}

        QScrollArea {{ border: none; background: transparent; }}
        """)

    # ── File actions ────────────────────────────────────────────────────────

    def _open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Audio Files", "",
            "Audio Files (*.mp3 *.flac *.ogg *.opus *.m4a *.aac *.mp4 *.wav *.aif *.aiff *.wv)"
        )
        if paths:
            self._load_paths(paths)

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Folder")
        if folder:
            self._load_paths([folder])

    def _load_paths(self, paths: list[str]):
        self._show_status("Loading…", False)
        thread = QThread(self)
        worker = LoadWorker(paths)
        worker.moveToThread(thread)
        
        # Keep strong references to prevent garbage collection
        if not hasattr(self, '_workers'):
            self._workers = []
        self._workers.append((thread, worker))
        
        thread.started.connect(worker.run)
        worker.done.connect(self._on_load_done)
        worker.finished.connect(thread.quit)
        
        def cleanup():
            worker.deleteLater()
            thread.deleteLater()
            if (thread, worker) in self._workers:
                self._workers.remove((thread, worker))
                
        thread.finished.connect(cleanup)
        thread.start()

    def _on_load_done(self, tags: list):
        self._file_list.add_tags(tags)
        n = len(tags)
        if n:
            self._show_status(f"Loaded {n} file(s).", False)
        else:
            self._show_status("No supported audio files found.", True)

    def _save_all(self):
        tags = self._file_list.all_tags()
        if not tags:
            return
        self._show_status("Saving…", False)
        ok = fail = 0
        for tag in tags:
            try:
                save_tag(tag)
                ok += 1
            except Exception as e:
                print(f"[save_all] {tag.path}: {e}")
                fail += 1
        if fail == 0:
            self._show_status(f"Saved {ok} files.", False)
        else:
            self._show_status(f"{ok} saved, {fail} failed.", True)

    def _on_single_selected(self, tag: AudioTag):
        self._editor.load_single(tag)

    def _on_batch_selected(self, tags: list[AudioTag]):
        self._editor.load_batch(tags)

    def _on_selection_cleared(self):
        self._editor.clear()

    def _show_status(self, msg: str, is_error: bool):
        color = "#e05555" if is_error else ("#5dbf8a" if self._dark else "#1a7a40")
        self._status.showMessage(msg)
        self._status.setStyleSheet(
            f"QStatusBar {{ color: {color}; font-size: 12px; }}"
        )

    # ── Drag & Drop ─────────────────────────────────────────────────────────

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        if paths:
            self._load_paths(paths)
