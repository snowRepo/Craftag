"""
main.py — Craftag entry point.
Run: python main.py
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from craftag_py.ui.main_window import MainWindow


def main():
    # High-DPI support (handled automatically in Qt6)
    app = QApplication(sys.argv)
    app.setApplicationName("Craftag")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("DevApps")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
