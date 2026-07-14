"""Reusable UI widgets."""
from __future__ import annotations
from PySide6.QtWidgets import QLabel, QFrame
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QPainter, QColor, QFont, QPainterPath


class ArtLabel(QLabel):
    """Clickable 110×110 artwork thumbnail that accepts image drops.
    Supports light/dark mode placeholder via set_dark()."""

    clicked      = Signal()
    file_dropped = Signal(str)

    SIZE = 110

    # Placeholder colors per theme
    _DARK_BG     = "#252830"
    _DARK_BORDER = "#3a3e52"
    _DARK_TEXT   = "#555870"

    _LIGHT_BG     = "#f0f0f4"
    _LIGHT_BORDER = "#c8c8d0"
    _LIGHT_TEXT   = "#a0a0b0"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self._has_art   = False
        self._hovered   = False
        self._dark      = True
        self._pixmap_raw: QPixmap | None = None
        self._pixmap_scaled: QPixmap | None = None
        self._set_placeholder()

    # ── Theme ───────────────────────────────────────────────────────────────

    def set_dark(self, dark: bool):
        self._dark = dark
        if not self._has_art:
            self._set_placeholder()       # re-apply with correct colours
        else:
            # Update image border colour for current theme
            border = "#3a3e52" if dark else "#d0d0d8"
            super().setStyleSheet(f"""
                ArtLabel {{
                    border: 1.5px solid {border};
                    border-radius: 14px;
                    background: transparent;
                }}
            """)

    # ── Appearance ──────────────────────────────────────────────────────────

    def _set_placeholder(self):
        self._has_art    = False
        self._pixmap_raw = None
        self._pixmap_scaled = None
        self.setText("🎵\nNo Art")
        bg     = self._DARK_BG     if self._dark else self._LIGHT_BG
        border = self._DARK_BORDER if self._dark else self._LIGHT_BORDER
        color  = self._DARK_TEXT   if self._dark else self._LIGHT_TEXT
        self.setStyleSheet(f"""
            ArtLabel {{
                border: 2px dashed {border};
                border-radius: 14px;
                background: {bg};
                color: {color};
                font-size: 11px;
            }}
        """)

    def set_pixmap(self, px: QPixmap):
        self._has_art    = True
        self._pixmap_raw = px
        self.setText("")
        scaled = px.scaled(
            self.SIZE, self.SIZE,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        if scaled.width() > self.SIZE or scaled.height() > self.SIZE:
            x = (scaled.width()  - self.SIZE) // 2
            y = (scaled.height() - self.SIZE) // 2
            scaled = scaled.copy(x, y, self.SIZE, self.SIZE)
        border = "#3a3e52" if self._dark else "#d0d0d8"
        self.setStyleSheet(f"""
            ArtLabel {{
                border: 1.5px solid {border};
                border-radius: 14px;
                background: transparent;
            }}
        """)
        self._pixmap_scaled = scaled
        self.update()

    def clear_art(self):
        self.clear()
        self._set_placeholder()

    # ── Hover overlay ────────────────────────────────────────────────────────

    def enterEvent(self, e):
        self._hovered = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        # Let the stylesheet draw the background and border
        super().paintEvent(e)
        
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        
        # Draw the image clipped to the rounded rect
        if self._has_art and self._pixmap_scaled:
            path = QPainterPath()
            # Inset by 1.5px (the border width) to not draw over the border
            path.addRoundedRect(1.5, 1.5, self.width() - 3, self.height() - 3, 12.5, 12.5)
            p.setClipPath(path)
            p.drawPixmap(0, 0, self._pixmap_scaled)
            
        # Draw hover overlay
        if self._hovered:
            path = QPainterPath()
            path.addRoundedRect(0, 0, self.width(), self.height(), 14, 14)
            p.setClipPath(path)
            p.fillRect(0, 0, self.width(), self.height(), QColor(0, 0, 0, 130))
            p.setPen(QColor(255, 255, 255, 220))
            p.setFont(QFont("-apple-system", 11, QFont.Medium))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Change" if self._has_art else "Set Art")
        p.end()

    # ── Mouse / Drop ─────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".jpg", ".jpeg", ".png",
                                      ".gif", ".bmp", ".webp")):
                self.file_dropped.emit(path)
                break


class HSep(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Plain)
        self.setFixedHeight(1)
        self.setObjectName("hsep")
