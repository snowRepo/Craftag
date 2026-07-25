"""
main_window.py — Craftag main window.
Supports light/dark theme toggle wired through FileListPanel's header.
"""
from __future__ import annotations
import os
import sys

def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, handling PyInstaller's _MEIPASS on Windows."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar, QFileDialog,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QApplication,
    QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, QThread, QObject, Signal, QSettings, QTimer
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent, QPixmap, QKeySequence, QShortcut, QAction, QGuiApplication, QPainter, QColor
import sys

from craftag_py.__version__ import VERSION
from craftag_py.core.tag_io import AudioTag, read_tag, read_folder, save_tag
from craftag_py.ui.file_list import FileListPanel
from craftag_py.ui.editor_panel import EditorPanel

class CustomProgressBar(QLabel):
    """A crash-proof progress bar that renders completely off-screen to avoid macOS QBackingStore bugs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self._max = 100
        self._val = 0
        self._dark = False

    def setMaximum(self, m: int):
        self._max = max(1, m)
        self._render()
        
    def setValue(self, v: int):
        self._val = max(0, min(self._max, v))
        self._render()

    def set_dark(self, is_dark: bool):
        self._dark = is_dark
        self._render()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._render()

    def _render(self):
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        try:
            # Draw track background
            bg_color = QColor("#303030") if self._dark else QColor("#e0e0e0")
            p.fillRect(0, 0, w, h, bg_color)
            # Draw progress fill
            if self._max > 0:
                pw = int(w * (self._val / self._max))
                fg_color = QColor("#ffffff") if self._dark else QColor("#007aff")
                p.fillRect(0, 0, pw, h, fg_color)
        finally:
            p.end()
        self.setPixmap(pm)


# ── Background loader ──────────────────────────────────────────────────────────

class LoadWorker(QObject):
    finished = Signal()

    def __init__(self, paths: list[str]):
        super().__init__()
        self._paths = paths
        self.results: list[AudioTag] = []

    def run(self):
        try:
            for p in self._paths:
                try:
                    if os.path.isdir(p):
                        self.results.extend(read_folder(p))
                    elif os.path.isfile(p):
                        tag = read_tag(p)
                        if tag:
                            self.results.append(tag)
                except Exception as e:
                    print(f"[LoadWorker] skipping {p}: {e}")
        finally:
            # Always emit finished — even on total failure — so UI never hangs
            self.finished.emit()


# ── Background saver ──────────────────────────────────────────────────────

class SaveWorker(QObject):
    """Saves a list of AudioTag objects on a background thread.

    IMPORTANT: This worker must NOT mutate any AudioTag fields.
    AudioTag objects are shared with the main thread; mutating them
    from a background thread causes data races and crashes.
    Instead we collect the successfully-saved tags and send them back
    to the main thread via the `finished` signal, where the main thread
    can safely reset their dirty state.
    """
    progress  = Signal(int, int)   # (done_count, total)
    finished  = Signal(list, int)  # (saved_paths: list[str], fail_count)

    def __init__(self, tags: list[AudioTag]):
        super().__init__()
        self._tags = tags

    def run(self):
        saved_paths = []
        fail = 0
        total = len(self._tags)
        for i, tag in enumerate(self._tags, 1):
            try:
                save_tag(tag)
                saved_paths.append(tag.path)
            except Exception as e:
                print(f"[SaveWorker] {tag.path}: {e}")
                fail += 1
            # NOTE: progress is connected with QueuedConnection so this
            # emit is safe to call from the worker thread — PySide6 will
            # marshal it onto the main thread before executing the slot.
            self.progress.emit(i, total)
        # Emitting strings (primitive type) is safely handled by Qt's QueuedConnection
        # without risking Python garbage collection races on custom objects.
        self.finished.emit(saved_paths, fail)


# ── Update checker ─────────────────────────────────────────────────────────────

class UpdateWorker(QObject):
    """Fetches the published version.json and compares it to the running version.

    Emits exactly one signal:
      up_to_date()                       — already on latest
      update_available(latest, dl_url)   — newer version exists
      error(msg)                         — network / parse failure
    """
    up_to_date       = Signal()
    update_available = Signal(str, str)   # (latest_version, download_url)
    error            = Signal(str)

    _VERSION_URL = (
        "https://raw.githubusercontent.com/snowRepo/Craftag/main/version.json"
    )

    def run(self):
        try:
            import json
            import urllib.request
            import ssl
            from craftag_py.__version__ import VERSION

            # Allow fetching over HTTPS seamlessly, ignoring bundled CA issues in Pyinstaller on Mac
            ctx = ssl._create_unverified_context()
            
            req = urllib.request.Request(self._VERSION_URL, headers={"User-Agent": f"Craftag/{VERSION}"})
            with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
                raw_data = resp.read()
                
            data = json.loads(raw_data)

            latest = data.get("version", "").strip()
            dl_url = data.get("download_url", "https://devapps-online.vercel.app")

            if latest and latest != VERSION:
                self.update_available.emit(latest, dl_url)
            else:
                self.up_to_date.emit()
        except Exception as e:
            self.error.emit(f"Network error: {e}\nPlease check your internet connection and try again.")

class DownloadWorker(QObject):
    progress = Signal(int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, url: str, filename: str):
        super().__init__()
        self._url = url
        self._filename = filename

    def run(self):
        try:
            import urllib.request
            import ssl
            from pathlib import Path

            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(self._url, headers={"User-Agent": "Craftag/Updater"})
            
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                dl_path = Path.home() / "Downloads" / self._filename
                total_length = resp.headers.get('content-length')
                
                if total_length is None:
                    self.progress.emit(50)
                    with open(dl_path, 'wb') as f:
                        f.write(resp.read())
                    self.progress.emit(100)
                else:
                    total_length = int(total_length)
                    dl = 0
                    with open(dl_path, 'wb') as f:
                        while True:
                            chunk = resp.read(8192)
                            if not chunk:
                                break
                            dl += len(chunk)
                            f.write(chunk)
                            done = int(100 * dl / total_length)
                            self.progress.emit(done)
                            
                self.finished.emit(str(dl_path))
                
        except Exception as e:
            self.error.emit(f"Download failed: {e}\nPlease check your internet connection.")

class AboutDialog(QDialog):
    def __init__(self, parent=None, dark=False, startup_mode=False):
        super().__init__(parent)
        self.setWindowTitle("Craftag EULA" if startup_mode else "About Craftag")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header (Logo + Title)
        header_layout = QHBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        logo_lbl = QLabel()
        icon_path = get_resource_path("logo.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            logo_lbl.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header_layout.addWidget(logo_lbl)
        
        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        title_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_lbl = QLabel("Craftag")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold;")
        title_layout.addWidget(title_lbl)
        version_lbl = QLabel(f"Version {VERSION}")
        title_layout.addWidget(version_lbl)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        if startup_mode:
            # Startup mode: show full EULA
            self.setFixedSize(540, 560)
            
            # EULA text
            self.text_edit = QTextEdit()
            self.text_edit.setReadOnly(True)
            license_path = get_resource_path("license.txt")
            if os.path.exists(license_path):
                with open(license_path, "r", encoding="utf-8") as f:
                    self.text_edit.setPlainText(f.read())
            else:
                self.text_edit.setPlainText("End User License Agreement (EULA) not found.")
                
            layout.addWidget(self.text_edit)
        else:
            # About mode: compact about pane
            self.setFixedSize(360, 240)
            
            # Spacer
            layout.addSpacing(8)
            
            # Description
            desc_lbl = QLabel("A simple, cross-platform audio tag editor.")
            desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_lbl.setWordWrap(True)
            layout.addWidget(desc_lbl)
            
            # Spacer
            layout.addSpacing(12)
            
            # Copyright
            copyright_lbl = QLabel("© 2026 Craftag\nAll rights reserved.")
            copyright_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            copyright_color = "#666666" if dark else "#888888"
            copyright_lbl.setStyleSheet(f"font-size: 11px; color: {copyright_color};")
            layout.addWidget(copyright_lbl)
            
            layout.addStretch()
        
        if startup_mode:
            # Buttons for the EULA modal only.
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()

            decline_btn = QPushButton("Decline")
            decline_btn.setFixedSize(100, 32)
            decline_btn.setObjectName("declineBtn")
            decline_btn.clicked.connect(self.reject)
            btn_layout.addWidget(decline_btn)
            
            agree_btn = QPushButton("Agree")
            agree_btn.setFixedSize(100, 32)
            agree_btn.clicked.connect(self.accept)
            btn_layout.addWidget(agree_btn)
            
            layout.addLayout(btn_layout)
        
        bg = "#1e1e1e" if dark else "#ffffff"
        text = "#ffffff" if dark else "#000000"
        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg}; color: {text}; }}
            QLabel {{ color: {text}; }}
            QTextEdit {{
                background-color: {"#2d2d2d" if dark else "#f5f5f5"};
                color: {text};
                border: 1px solid {"#444" if dark else "#ccc"};
                border-radius: 6px;
                padding: 12px;
            }}
            QPushButton {{
                background-color: {"#333333" if dark else "#e5e5e5"};
                color: {text};
                border-radius: 6px;
                border: 1px solid {"#444444" if dark else "#cccccc"};
            }}
            QPushButton:hover {{
                background-color: {"#444444" if dark else "#d4d4d4"};
            }}
            QPushButton#declineBtn {{
                background-color: transparent;
                color: {text};
                border: 1px solid {"#444" if dark else "#ccc"};
            }}
            QPushButton#declineBtn:hover {{
                background-color: {"#333" if dark else "#eee"};
            }}
        """)

# ── Main Window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # On macOS the menu bar already shows the app name; an empty window title
        # gives a cleaner look and lets us use it purely for track context.
        # On Windows/Linux we keep "Craftag" so the taskbar is always labelled.
        import sys
        if sys.platform != "darwin":
            self.setWindowTitle("Craftag")
        else:
            self.setWindowTitle("")
        self.setMinimumSize(820, 540)
        self.resize(1060, 660)
        self.setAcceptDrops(True)
        self._dark = False

        # Window icon — use the same bundled-asset resolver used in main.py
        # so the icon is found inside a PyInstaller package on all platforms.
        icon_name = "logo.ico" if sys.platform == "win32" else "logo.png"
        icon_path = get_resource_path(icon_name)
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._sync_system_theme()

        # React to live system appearance changes (macOS dark/light toggle)
        # Store as instance var so we can disconnect it in closeEvent
        self._style_hints = QGuiApplication.styleHints()
        self._style_hints.colorSchemeChanged.connect(self._on_color_scheme_changed)

        QTimer.singleShot(0, self._check_eula)

    def _check_eula(self):
        settings = QSettings("DevApps", "Craftag")
        if not settings.value("eula_agreed", False, type=bool):
            dlg = AboutDialog(self, dark=self._dark, startup_mode=True)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                settings.setValue("eula_agreed", True)
            else:
                QApplication.quit()

    def closeEvent(self, event):
        """Clean shutdown: disconnect live signals and join worker threads
        to prevent PySide6/macOS segfaults during Qt object teardown."""
        # Disconnect the system color-scheme signal FIRST — if it fires during
        # teardown while the window's Python object is partially destroyed it
        # causes a segfault on macOS.
        try:
            self._style_hints.colorSchemeChanged.disconnect(self._on_color_scheme_changed)
        except Exception:
            pass

        # Gracefully stop any in-flight load/save/update worker threads.
        # We wait up to 2 s per thread so they can finish writing to disk.
        for thread, _ in list(getattr(self, "_workers", [])):
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(2000)
            except Exception:
                pass

        for thread, _ in list(getattr(self, "_update_workers", [])):
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(1000)
            except Exception:
                pass

        super().closeEvent(event)

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setObjectName("mainSplitter")

        self._file_list = FileListPanel()
        self._file_list.setMinimumWidth(200)
        self._file_list.setMaximumWidth(300)
        self._file_list.set_dark(self._dark)  # Initialize theme button state
        self._file_list.open_files_requested.connect(self._open_files)
        self._file_list.open_folder_requested.connect(self._open_folder)
        self._file_list.save_all_requested.connect(self._save_all)
        self._file_list.single_selected.connect(self._on_single_selected)
        self._file_list.batch_selected.connect(self._on_batch_selected)
        self._file_list.selection_cleared.connect(self._on_selection_cleared)
        self._file_list.status_message.connect(self._show_status)
        splitter.addWidget(self._file_list)

        self._editor = EditorPanel()
        self._editor.status_message.connect(self._show_status)
        self._editor.tags_dirtied.connect(self._file_list.update_items)
        self._editor.tags_renamed.connect(self._file_list.on_tags_renamed)
        self._editor.set_dark(self._dark)   # sync initial theme
        splitter.addWidget(self._editor)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.setCentralWidget(splitter)

        self._status = QStatusBar()
        self._status.setObjectName("statusBar")
        self.setStatusBar(self._status)

        self._progress = CustomProgressBar()
        self._progress.setFixedHeight(4)
        self._progress.hide()
        self._status.addPermanentWidget(self._progress)
        
        self._build_menu()

    def _build_menu(self):
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        action_open_files = QAction("Open Files...", self)
        action_open_files.setShortcut(QKeySequence.StandardKey.Open)
        action_open_files.triggered.connect(self._open_files)
        file_menu.addAction(action_open_files)

        action_open_folder = QAction("Open Folder...", self)
        action_open_folder.setShortcut(QKeySequence("Ctrl+Shift+O"))
        action_open_folder.triggered.connect(self._open_folder)
        file_menu.addAction(action_open_folder)

        file_menu.addSeparator()

        action_save_all = QAction("Save All", self)
        action_save_all.setMenuRole(QAction.MenuRole.NoRole)
        action_save_all.setShortcut(QKeySequence.StandardKey.Save)
        action_save_all.triggered.connect(self._save_all)
        file_menu.addAction(action_save_all)
        
        file_menu.addSeparator()
        
        action_quit = QAction("Quit", self)
        action_quit.setMenuRole(QAction.MenuRole.QuitRole)
        action_quit.setShortcut(QKeySequence.StandardKey.Quit)
        action_quit.triggered.connect(QApplication.quit)
        file_menu.addAction(action_quit)

        # Help Menu
        help_menu = menubar.addMenu("&Help")

        self._action_check_updates = QAction("Check for Updates...", self)
        self._action_check_updates.setMenuRole(QAction.MenuRole.NoRole)
        self._action_check_updates.triggered.connect(self._check_for_updates)
        help_menu.addAction(self._action_check_updates)

        action_about = QAction("About Craftag", self)
        action_about.setMenuRole(QAction.MenuRole.AboutRole)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

        action_quit.setMenuRole(QAction.MenuRole.QuitRole)

    # ── Theme ───────────────────────────────────────────────────────────────

    def _sync_system_theme(self):
        """Read the current system color scheme and apply it."""
        from PySide6.QtCore import Qt as _Qt
        scheme = QGuiApplication.styleHints().colorScheme()
        self._dark = (scheme == _Qt.ColorScheme.Dark)
        self._file_list.set_dark(self._dark)
        self._editor.set_dark(self._dark)
        self._apply_stylesheet()

    def _on_color_scheme_changed(self, scheme):
        """Slot called when the OS toggles dark/light mode."""
        from PySide6.QtCore import Qt as _Qt
        self._dark = (scheme == _Qt.ColorScheme.Dark)
        self._file_list.set_dark(self._dark)
        self._editor.set_dark(self._dark)
        self._apply_stylesheet()

    def _show_about(self):
        dlg = AboutDialog(self, dark=self._dark)
        dlg.exec()

    # ── Check for updates ────────────────────────────────────────────

    def _check_for_updates(self):
        """Non-blocking 'Checking...' dialog + background update worker.
        Uses show() (not exec()) so the main event loop keeps running.
        Connects to proper QObject slots on self so AutoConnection correctly
        promotes to QueuedConnection across the thread boundary."""
        self._action_check_updates.setEnabled(False)
        self._action_check_updates.setText("Checking\u2026")

        # Non-blocking modal indicator — show(), NOT exec()
        checking_dlg = QDialog(self)
        checking_dlg.setWindowTitle("Check for Updates")
        checking_dlg.setWindowFlags(
            checking_dlg.windowFlags()
            & ~Qt.WindowType.WindowCloseButtonHint
        )
        checking_dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        checking_dlg.setFixedSize(300, 72)
        chk_layout = QVBoxLayout(checking_dlg)
        chk_layout.setContentsMargins(20, 16, 20, 16)
        chk_lbl = QLabel("Checking for updates\u2026")
        chk_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk_layout.addWidget(chk_lbl)
        # Store on self so result slots (QObject methods) can close it
        self._checking_dlg = checking_dlg
        checking_dlg.show()

        thread = QThread(self)
        worker = UpdateWorker()
        worker.moveToThread(thread)

        if not hasattr(self, "_update_workers"):
            self._update_workers: list = []
        self._update_workers.append((thread, worker))

        thread.started.connect(worker.run)

        def _cleanup():
            if (thread, worker) in self._update_workers:
                self._update_workers.remove((thread, worker))
            worker.deleteLater()
            thread.deleteLater()
            self._action_check_updates.setEnabled(True)
            self._action_check_updates.setText("Check for Updates...")

        # Connect to proper QObject methods on self (main thread).
        # AutoConnection detects cross-thread QObject target and uses
        # QueuedConnection — safe, no thread-affinity warnings.
        worker.up_to_date.connect(self._on_update_up_to_date)
        worker.update_available.connect(self._on_update_available)
        worker.error.connect(self._on_update_error)
        for sig in (worker.up_to_date, worker.update_available, worker.error):
            sig.connect(thread.quit)
        thread.finished.connect(_cleanup, Qt.ConnectionType.QueuedConnection)
        thread.start()


    def _close_checking_dlg(self):
        """Close the update-checking indicator if it is still visible."""
        dlg = getattr(self, "_checking_dlg", None)
        if dlg is not None:
            try:
                dlg.accept()
            except Exception:
                pass
            self._checking_dlg = None

    def _on_update_up_to_date(self):
        self._close_checking_dlg()
        from craftag_py.__version__ import VERSION
        QMessageBox.information(
            self, "Up to Date",
            f"You are running the latest version of Craftag ({VERSION})."
        )

    def _on_update_available(self, latest: str, dl_url: str):
        self._close_checking_dlg()
        from craftag_py.__version__ import VERSION
        import platform
        import os
        import subprocess

        dlg = QDialog(self)
        dlg.setWindowTitle("Update Available")
        dlg.setFixedWidth(380)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        lbl = QLabel(f"<b>Craftag {latest} is available!</b>")
        layout.addWidget(lbl)
        layout.addWidget(QLabel(f"You are on version {VERSION}."))

        # Use native QProgressBar — reliable cross-platform rendering
        prg = QProgressBar()
        prg.setRange(0, 100)
        prg.setValue(0)
        prg.setFixedHeight(8)
        prg.setTextVisible(False)
        prg.hide()
        layout.addWidget(prg)

        status_lbl = QLabel("")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        status_lbl.hide()
        layout.addWidget(status_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        later_btn = QPushButton("Later")
        later_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(later_btn)

        dl_btn = QPushButton("Download Update")

        def _start_download():
            dl_btn.setEnabled(False)
            later_btn.setEnabled(False)
            prg.show()
            status_lbl.show()
            status_lbl.setText("Starting download…")
            dlg.setFixedHeight(dlg.sizeHint().height())

            if platform.system() == "Windows":
                filename = "Craftag-Windows-Installer.exe"
            else:
                filename = "Craftag-macOS.dmg"

            github_url = f"https://github.com/snowRepo/Craftag/releases/download/v{latest}/{filename}"

            self._dl_thread = QThread(dlg)
            self._dl_worker = DownloadWorker(github_url, filename)
            self._dl_worker.moveToThread(self._dl_thread)
            self._dl_thread.started.connect(self._dl_worker.run)

            def _on_prog(v):
                prg.setValue(v)
                status_lbl.setText(f"Downloading…  {v}%")

            def _on_fin(path):
                prg.setValue(100)
                status_lbl.hide()
                prg.hide()
                lbl.setText("<b>Ready to install!</b>")
                dl_btn.setText("Install Now")
                dl_btn.setEnabled(True)
                later_btn.setEnabled(True)

                dl_btn.clicked.disconnect()

                def _do_install():
                    try:
                        if platform.system() == "Windows":
                            os.startfile(path)
                        else:
                            subprocess.Popen(["open", path])
                    except Exception:
                        pass
                    # Close the dialog cleanly, then quit the app after the
                    # event loop has had a chance to flush pending events.
                    dlg.accept()
                    QTimer.singleShot(200, QApplication.quit)

                dl_btn.clicked.connect(_do_install)

            def _on_err(msg):
                prg.hide()
                status_lbl.hide()
                lbl.setText("<b>Download failed.</b>")
                dl_btn.setEnabled(False)
                later_btn.setEnabled(True)
                QMessageBox.warning(dlg, "Download Failed", msg)

            # QueuedConnection: slots run on GUI thread (safe widget access)
            self._dl_worker.progress.connect(_on_prog, Qt.ConnectionType.QueuedConnection)
            self._dl_worker.finished.connect(_on_fin, Qt.ConnectionType.QueuedConnection)
            # Worker error could be handled gracefully, but we just print for now
            self._dl_thread.start()

        dl_btn.clicked.connect(_start_download)
        btn_row.addWidget(dl_btn)

        layout.addLayout(btn_row)
        dlg.exec()

    def _on_update_error(self, msg: str):
        self._close_checking_dlg()
        QMessageBox.warning(
            self, "Update Check Failed",
            f"Could not check for updates:\n{msg}"
        )

    def _apply_stylesheet(self):
        dark = self._dark
        if dark:
            BG          = "#161616"
            SIDEBAR_BG  = "#111111"
            HEADER_BG   = "#1a1a1a"
            BORDER      = "#2a2a2a"
            SEP         = "#2a2a2a"
            TEXT        = "#e8e8e8"
            TEXT_MUTED  = "#787878"
            TEXT_SUBTLE = "#404040"
            INPUT_BG    = "#1e1e1e"
            INPUT_BOR   = "#333333"
            LIST_ITEM   = "#d0d0d0"
            LIST_SEL    = "rgba(255,255,255,0.10)"
            LIST_HOVER  = "rgba(255,255,255,0.04)"
            STATUS_BG   = "#0e0e0e"
            STATUS_BOR  = "#222222"
            HINT_COL    = "#383838"
            SCROLL_TH   = "#303030"
            SCROLL_HV   = "#484848"
            BTN_BG      = "#202020"
            BTN_BOR     = "#303030"
            BTN_COL     = "#888888"
            BTN_HV_BG   = "#282828"
            BTN_HV_BOR  = "#444444"
            BTN_HV_COL  = "#cccccc"
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
            padding: 0;
        }}
        #iconBtn:hover {{
            background: {BTN_HV_BG};
            border-color: {TEXT_MUTED};
            color: {TEXT};
        }}
        #iconBtn:pressed {{ background: {BTN_BG}; }}
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
        #textBtn:hover {{ color: {TEXT}; }}
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



        /* Save All — neutral style */
        #sidebarSaveBtn {{
            background: {BTN_BG};
            border: 1px solid {BORDER};
            border-radius: 5px;
            color: {TEXT};
            font-size: 11px;
            font-weight: 500;
            padding: 0 8px;
        }}
        #sidebarSaveBtn:hover {{
            background: {BTN_HV_BG};
            border-color: {TEXT_MUTED};
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
            color: {TEXT};
        }}
        
        #itemArtistLbl {{
            color: {"#aaaaaa" if dark else "#666666"};
        }}
        
        #itemRemoveBtn {{
            background: transparent;
            color: {TEXT_MUTED};
            border: none;
            font-size: 14px;
            font-weight: normal;
            padding-bottom: 2px;
        }}
        #itemRemoveBtn:hover {{
            color: {DANGER};
            background: {"rgba(224,85,85,0.1)" if dark else "rgba(217,64,64,0.07)"};
            border-radius: 4px;
        }}
        
        #formatBadge {{
            background-color: {"rgba(140, 140, 150, 0.25)" if dark else "rgba(0, 0, 0, 0.08)"};
            color: {"#aaaaaa" if dark else "#555555"};
            border-radius: 5px;
            padding: 1px 4px;
            font-size: 9px;
            font-weight: 700;
            margin-top: 1px;
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
        
        QTabWidget::pane {{
            border: none;
            border-top: 1px solid {BORDER};
        }}
        QTabBar::tab {{
            padding: 8px 16px;
            margin: 0;
            background: transparent;
            color: {TEXT_MUTED};
        }}
        QTabBar::tab:selected {{
            color: {TEXT};
            font-weight: 600;
        }}
        QTabBar {{
            alignment: center;
        }}

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
            selection-background-color: {LIST_SEL};
        }}
        QLineEdit:focus {{
            border-color: {TEXT_MUTED};
            background: {INPUT_BG};
        }}
        QLineEdit:disabled {{ color: {TEXT_SUBTLE}; }}

        QComboBox {{
            background: {INPUT_BG};
            border: 1px solid {INPUT_BOR};
            border-radius: 6px;
            color: {TEXT};
            padding: 4px 8px;
            font-size: 13px;
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {TEXT_MUTED};
            margin-right: 8px;
        }}
        QComboBox:focus {{
            border-color: {TEXT_MUTED};
            background: {INPUT_BG};
        }}
        QComboBox QAbstractItemView {{
            border: 1px solid {BORDER};
            border-radius: 6px;
            background: {BG};
            outline: none;
            selection-background-color: {LIST_SEL};
        }}

        QTextEdit {{
            background: {INPUT_BG};
            border: 1px solid {INPUT_BOR};
            border-radius: 6px;
            color: {TEXT};
            font-size: 13px;
            padding: 8px;
        }}
        QTextEdit:focus {{
            border-color: {TEXT_MUTED};
            background: {INPUT_BG};
        }}

        /* ── Tabs ── */
        QTabWidget::pane {{
            border: none;
            background: transparent;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {TEXT_MUTED};
            padding: 10px 16px;
            border-bottom: 2px solid transparent;
            font-size: 13px;
            font-weight: 500;
        }}
        QTabBar::tab:hover {{
            color: {TEXT};
            background: {LIST_HOVER};
        }}
        QTabBar::tab:selected {{
            color: {TEXT};
            border-bottom: 2px solid {TEXT_MUTED};
        }}

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
            color: {TEXT};
            border-color: {BORDER};
            background: transparent;
        }}
        QPushButton#smallDangerBtn:hover {{
            background: {BTN_HV_BG};
            border-color: {TEXT_MUTED};
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
            color: {TEXT_MUTED};
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
        worker.finished.connect(thread.quit)

        def cleanup():
            # Process loaded tags safely on the main thread, bypassing signal payloads.
            self._file_list.add_tags(worker.results)
            n = len(worker.results)
            if n:
                self._show_status(f"Loaded {n} file(s).", False)
            else:
                self._show_status("No supported audio files found.", True)

            worker.deleteLater()
            thread.deleteLater()
            if (thread, worker) in self._workers:
                self._workers.remove((thread, worker))

        # QueuedConnection is required here: thread.finished is emitted from the
        # worker thread, and Python callables have no Qt thread affinity, so
        # AutoConnection would call cleanup() directly on the worker thread.
        thread.finished.connect(cleanup, Qt.ConnectionType.QueuedConnection)
        thread.start()

    def _save_all(self):
        try:
            self._editor.commit_to_memory()
            tags = [t for t in self._file_list.all_tags() if t.is_dirty]
            if not tags:
                self._show_status("No changes to save.", False)
                return
            self._show_status(f"Saving 0 / {len(tags)}…", False)
            self._file_list.set_saving(True)

            self._progress.setMaximum(len(tags))
            self._progress.setValue(0)
            self._progress.show()

            thread = QThread(self)
            worker = SaveWorker(tags)
            worker.moveToThread(thread)

            if not hasattr(self, '_workers'):
                self._workers = []
            self._workers.append((thread, worker))

            thread.started.connect(worker.run)
            
            def on_progress(done, total):
                self._show_status(f"Saving {done} / {total}…", False)
                self._progress.setValue(done)

            # CRITICAL: must be QueuedConnection so that on_progress always
            # executes on the main (GUI) thread, not on the QThread worker.
            # Without this, PySide6 has no thread affinity for a plain Python
            # closure and dispatches it synchronously on the worker thread,
            # causing QWidget repaints from a non-GUI thread → segfault.
            worker.progress.connect(on_progress, Qt.ConnectionType.QueuedConnection)
            worker.finished.connect(self._on_save_all_done, Qt.ConnectionType.QueuedConnection)
            worker.finished.connect(lambda *_: thread.quit(), Qt.ConnectionType.QueuedConnection)

            def cleanup():
                worker.deleteLater()
                thread.deleteLater()
                if (thread, worker) in self._workers:
                    self._workers.remove((thread, worker))
                self._file_list.set_saving(False)
                self._progress.hide()

            # QueuedConnection is CRITICAL: cleanup() touches GUI widgets
            # (set_saving, progress.hide). Without QueuedConnection, PySide6
            # calls cleanup() directly on the worker thread — illegal GUI
            # access from a non-GUI thread — segfault.
            thread.finished.connect(cleanup, Qt.ConnectionType.QueuedConnection)
            thread.start()
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[MainWindow._save_all] Exception:\n{tb}")
            QMessageBox.critical(self, "Save All Error", f"An error occurred while saving: {e}\n\nSee console for details.")
            # Ensure UI isn't left in a saving state
            try:
                self._file_list.set_saving(False)
            except Exception:
                pass
            try:
                self._progress.hide()
            except Exception:
                pass

    def _on_save_all_done(self, saved_paths: list, fail: int):
        # Look up the actual AudioTag objects safely on the main GUI thread.
        # This completely avoids passing complex Python objects across the C++ thread boundary.
        path_to_tag = {t.path: t for t in self._file_list.all_tags()}
        saved_tags = [path_to_tag[p] for p in saved_paths if p in path_to_tag]

        # Reset dirty state on the main thread — safe because the worker
        # thread has already finished writing these tags to disk and will
        # not touch the AudioTag objects again.
        for tag in saved_tags:
            tag.is_dirty = False
            tag._staged_art = None
            tag._staged_art_mime = None
            tag._staged_art_removed = False
        ok = len(saved_tags)
        self._file_list.update_items()  # redraw list items to clear dirty dots
        if fail == 0:
            self._show_status(f"Saved {ok} file(s).", False)
        else:
            self._show_status(f"{ok} saved, {fail} failed.", True)

    def _on_single_selected(self, tag: AudioTag):
        self._editor.commit_to_memory()
        self._editor.load_single(tag)
        self._update_window_title([tag])

    def _on_batch_selected(self, tags: list[AudioTag]):
        self._editor.commit_to_memory()
        self._editor.load_batch(tags)
        self._update_window_title(tags)

    def _on_selection_cleared(self):
        self._editor.commit_to_memory()
        self._editor.clear()
        self._update_window_title([])

    def _update_window_title(self, tags: list):
        """Show track context in the window title (macOS only).

        On macOS the title bar is centred and visually separate from the
        dock/menu-bar app label, so using it for track context looks clean.

        On Windows the title is left-aligned next to the app icon, making
        the track name and the app name hard to distinguish.  The track
        name is already displayed prominently in the editor’s centred
        ``_lbl_title`` header, so we leave the Windows title bar as
        “Craftag” and let the editor header carry the context.
        """
        if sys.platform != "darwin":
            # Windows / Linux: keep the static app name.
            return

        if not tags:
            self.setWindowTitle("")
            return

        first = tags[0]
        title  = first.title  or first.filename
        artist = first.artist or ""

        if len(tags) == 1:
            track_text = f"{title} — {artist}" if artist else title
        else:
            track_text = f"{len(tags)} files selected"

        self.setWindowTitle(track_text)

    def _show_status(self, msg: str, is_error: bool):
        self._status.showMessage(msg)
        if is_error:
            self._status.setStyleSheet("QStatusBar { color: #e05555; }")
        else:
            self._status.setStyleSheet("")

    # ── Drag & Drop ─────────────────────────────────────────────────────────

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        paths = []
        for url in e.mimeData().urls():
            local = url.toLocalFile().strip()
            if local:
                # os.path.normpath fixes mixed-slash paths from Windows
                # Explorer (e.g. 'C:/Users/foo') and trailing separators
                # from some Linux file managers.
                paths.append(os.path.normpath(local))
        if paths:
            self._load_paths(paths)
