"""
main.py — Craftag entry point.
Run: python main.py
"""
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from craftag_py.__version__ import VERSION
from craftag_py.ui.main_window import MainWindow


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
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
