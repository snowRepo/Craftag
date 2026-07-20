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


def main():
    # High-DPI support (handled automatically in Qt6)
    app = QApplication(sys.argv)
    app.setApplicationName("Craftag")
    app.setApplicationDisplayName("Craftag")
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("DevApps")
    
    icon_path = os.path.join(os.path.dirname(__file__), "..", "logo.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
