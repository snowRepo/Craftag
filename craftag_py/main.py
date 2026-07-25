"""
main.py — Craftag entry point.
Run: python main.py
"""
import sys
import os
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from craftag_py.__version__ import VERSION
from craftag_py.ui.main_window import MainWindow

class CenterTabProxyStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_TabBar_Alignment:
            return int(Qt.AlignmentFlag.AlignCenter)
        return super().styleHint(hint, option, widget, returnData)

def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, handling PyInstaller's _MEIPASS on Windows."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

def main():
    # High-DPI support (handled automatically in Qt6)
    app = QApplication(sys.argv)
    
    # Enforce cross-platform style and strictly center tabs
    app.setStyle("Fusion")
    app.setStyle(CenterTabProxyStyle(app.style()))
    
    app.setApplicationName("Craftag")
    app.setApplicationDisplayName("Craftag")
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("DevApps")
    
    # Load optimal high-res icon (.ico encapsulates 16x16 to 256x256 cleanly for Windows)
    icon_name = "logo.ico" if sys.platform == "win32" else "logo.png"
    icon_path = get_resource_path(icon_name)
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    ret = app.exec()

    # ── PySide6 / macOS exit fix ─────────────────────────────────────────────
    # After app.exec() returns, Qt has already begun tearing down its C++
    # objects.  If Python's GC then runs (as sys.exit() triggers), it touches
    # the same memory Qt just freed → segfault.
    # Fix: explicitly delete the window so closeEvent fires in a clean state,
    # process any remaining deferred-deletion events, then use os._exit() to
    # skip Python GC teardown entirely.  This is the standard workaround for
    # the known PySide6 macOS shutdown crash (PYSIDE-2268).
    try:
        window.close()
        del window
        app.processEvents()   # flush any pending deleteLater() calls
    except Exception:
        pass
    os._exit(ret)


if __name__ == "__main__":
    main()
