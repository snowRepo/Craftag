"""Reusable UI widgets."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QLabel, QFrame, QApplication, QVBoxLayout, QWidget, QPushButton,
    QTabWidget, QStyleOptionButton, QStyle,
)
from PySide6.QtCore import Qt, Signal, QRect, QSize, QEvent
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QPainter, QColor, QFont, QPainterPath, QPalette, QIcon, QPen


# ── Image validation helpers ───────────────────────────────────────────────────

# (signature_bytes, mime_type) pairs in detection priority order
_IMAGE_SIGNATURES = (
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'\xff\xd8\xff',        'image/jpeg'),
    (b'GIF87a',              'image/gif'),
    (b'GIF89a',              'image/gif'),
    (b'BM',                  'image/bmp'),
)


def _sniff_mime(header: bytes) -> str | None:
    """Return the MIME type from the first 12 bytes of a file, or None if
    the bytes do not match any supported image signature."""
    for sig, mime in _IMAGE_SIGNATURES:
        if header.startswith(sig):
            return mime
    # WebP: 'RIFF' + 4 arbitrary bytes + 'WEBP'
    if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'image/webp'
    return None


def _is_valid_image_file(path: str) -> bool:
    """Return True if the file's header matches a recognised image signature.
    Reads only 12 bytes so it is fast even on network drives."""
    try:
        with open(path, 'rb') as f:
            header = f.read(12)
        return _sniff_mime(header) is not None
    except OSError:
        return False


class ArtLabel(QLabel):
    """Clickable 110×110 artwork thumbnail that accepts image drops.
    Supports light/dark mode placeholder via set_dark()."""

    clicked = Signal()
    file_dropped = Signal(str)

    SIZE = 110

    # Placeholder colors per theme
    _DARK_BG = "#252830"
    _DARK_BORDER = "#3a3e52"
    _DARK_TEXT = "#555870"

    _LIGHT_BG = "#f0f0f4"
    _LIGHT_BORDER = "#c8c8d0"
    _LIGHT_TEXT = "#a0a0b0"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._has_art = False
        self._hovered = False
        self._dark = False
        self._pixmap_raw: QPixmap | None = None
        self._pixmap_scaled: QPixmap | None = None
        self._set_placeholder()

    # ── Theme ───────────────────────────────────────────────────────────────

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_art()

    # ── Appearance ──────────────────────────────────────────────────────────

    def _set_placeholder(self):
        self._has_art = False
        self._pixmap_raw = None
        self._pixmap_scaled = None
        self._render_art()

    def set_pixmap(self, px: QPixmap):
        # Guard: never replace valid art with a broken / null image
        if px.isNull():
            return
        self._pixmap_raw = px
        scaled = px.scaled(
            self.SIZE, self.SIZE,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() > self.SIZE or scaled.height() > self.SIZE:
            x = (scaled.width() - self.SIZE) // 2
            y = (scaled.height() - self.SIZE) // 2
            scaled = scaled.copy(x, y, self.SIZE, self.SIZE)
        # Set _has_art only after we have a successfully scaled pixmap
        self._pixmap_scaled = scaled
        self._has_art = not scaled.isNull()
        self._render_art()

    def clear_art(self):
        self._set_placeholder()

    # ── Hover overlay ────────────────────────────────────────────────────────

    def enterEvent(self, e):
        self._hovered = True
        self._render_art()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self._render_art()
        super().leaveEvent(e)

    def _render_art(self):
        # Guard: don't paint if widget isn't properly sized yet
        if self.width() <= 0 or self.height() <= 0:
            return
        
        # Render entirely off-screen to a QPixmap to avoid macOS QBackingStore crashes
        pm = QPixmap(self.width(), self.height())
        pm.fill(Qt.GlobalColor.transparent)
        
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

            bg = self._DARK_BG if self._dark else self._LIGHT_BG
            border_c = self._DARK_BORDER if self._dark else self._LIGHT_BORDER
            
            # 1. Draw Base Background & Border
            path = QPainterPath()
            path.addRoundedRect(1, 1, self.width() - 2, self.height() - 2, 13, 13)
            
            if not self._has_art:
                # Placeholder: Background + Dashed border
                p.fillPath(path, QColor(bg))
                pen = QPen(QColor(border_c), 2.0, Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.drawPath(path)
            else:
                # Has Art: Solid border
                pen = QPen(QColor(border_c), 1.5, Qt.PenStyle.SolidLine)
                p.setPen(pen)
                p.drawPath(path)

            # 2. Draw Image or Text
            if self._has_art and self._pixmap_scaled:
                # Inset clip path slightly so we don't draw over the border
                clip_path = QPainterPath()
                clip_path.addRoundedRect(1.5, 1.5, self.width() - 3, self.height() - 3, 12.5, 12.5)
                p.setClipPath(clip_path)
                p.drawPixmap(0, 0, self._pixmap_scaled)
                p.setClipping(False)
            elif not self._has_art:
                # Draw placeholder text when no art
                p.setPen(QColor(self._DARK_TEXT if self._dark else self._LIGHT_TEXT))
                p.setFont(QFont(self.font().family(), 9, QFont.Weight.Normal))
                p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "🎵\nNo Art")

            # 3. Draw hover overlay
            if self._hovered:
                hover_path = QPainterPath()
                hover_path.addRoundedRect(0, 0, self.width(), self.height(), 14, 14)
                p.setClipPath(hover_path)
                p.fillRect(0, 0, self.width(), self.height(), QColor(0, 0, 0, 130))
                p.setPen(QColor(255, 255, 255, 220))
                p.setFont(QFont(self.font().family(), 11, QFont.Weight.Medium))
                p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter,
                           "Change Art" if self._has_art else "Set Art")
        finally:
            p.end()
            
        self.setPixmap(pm)

    # ── Mouse / Drop ─────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        for url in e.mimeData().urls():
            path = url.toLocalFile().strip()
            # Validate content by magic bytes, not just extension.
            # This prevents accidentally treating a dropped audio file or
            # document as album art.
            if path and _is_valid_image_file(path):
                self.file_dropped.emit(path)
                break


class SvgIconButton(QPushButton):
    """Button that renders an SVG icon.

    We avoid overriding ``paintEvent`` here because macOS native styles
    (QMacStyle) are highly sensitive to custom painters and can trigger
    QBackingStore recursion segfaults. Instead, we render the SVG to a
    QPixmap based on the palette text colour, and pass it to ``setIcon()``.
    Qt's QIcon engine automatically handles generating the disabled state.

    Args:
        svg_template: SVG source with literal ``{color}`` placeholder that is
            substituted with the current ``ButtonText`` palette colour.
        tooltip: Optional tooltip string.
        icon_size: Side-length (px) of the icon square drawn inside the button.
    """

    def __init__(self, svg_template: str, tooltip: str = "", icon_size: int = 18, parent=None):
        super().__init__(parent)
        self._svg_template = svg_template
        self._icon_size = icon_size
        if tooltip:
            self.setToolTip(tooltip)
        
        self.setIconSize(QSize(icon_size, icon_size))
        self._update_icon()

    def changeEvent(self, e):
        """Re-render the SVG if the application palette (e.g. dark mode) changes."""
        if e.type() == QEvent.Type.PaletteChange:
            self._update_icon()
        super().changeEvent(e)

    def _update_icon(self):
        # We only need to render the Normal state. QIcon automatically
        # generates a desaturated/translucent version for Disabled state.
        color = self.palette().color(QPalette.ColorGroup.Normal, QPalette.ColorRole.ButtonText).name()
        svg = self._svg_template.replace("{color}", color)

        pm = QPixmap()
        pm.loadFromData(svg.encode("utf-8"), "SVG")
        if not pm.isNull():
            self.setIcon(QIcon(pm))


class CenteredTabWidget(QTabWidget):
    """QTabWidget whose tab bar is always centred horizontally.

    Qt's QSS ``alignment: center`` on ``QTabBar`` is silently ignored by the
    Windows style engine, making tabs snap to the left on Windows regardless of
    the stylesheet.  Overriding ``resizeEvent`` (and ``tabInserted``) to
    programmatically reposition the tab bar is the only reliable
    cross-platform solution.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tabBar().setExpanding(False)

    def _center_tab_bar(self):
        tb = self.tabBar()
        x = max(0, (self.width() - tb.sizeHint().width()) // 2)
        tb.move(x, tb.y())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._center_tab_bar()

    def showEvent(self, e):
        super().showEvent(e)
        self._center_tab_bar()

    def tabInserted(self, index: int):
        super().tabInserted(index)
        self._center_tab_bar()

    def tabRemoved(self, index: int):
        super().tabRemoved(index)
        self._center_tab_bar()


class HSep(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setFixedHeight(1)
        self.setObjectName("hsep")


class StarRatingWidget(QLabel):
    """A premium, minimal 5-star rating widget."""
    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFixedHeight(28)
        self.setMinimumWidth(100)
        self.setSizePolicy(self.sizePolicy().Policy.Expanding, self.sizePolicy().Policy.Fixed)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value = 0
        self._hover_value = 0
        self._hovering = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._render_stars()
        
    def changeEvent(self, e):
        if e.type() == QEvent.Type.PaletteChange:
            self._render_stars()
        super().changeEvent(e)

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        if not isinstance(val, int):
            try:
                val = int(val)
            except Exception:
                val = 0
        self._value = max(0, min(5, val))
        self._render_stars()

    def clear(self):
        self.setValue(0)

    def leaveEvent(self, e):
        self._hovering = False
        self._render_stars()
        super().leaveEvent(e)

    def mouseMoveEvent(self, e):
        if not self.isEnabled():
            return
        self._hovering = True
        w = self.width() / 5.0
        x = e.position().x()
        self._hover_value = max(1, min(5, int(x / w) + 1))
        self._render_stars()
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        if not self.isEnabled():
            return
        if e.button() == Qt.MouseButton.LeftButton:
            w = self.width() / 5.0
            x = e.position().x()
            new_val = max(1, min(5, int(x / w) + 1))
            # Clicking the exact same star clears the rating
            if new_val == self._value:
                self._value = 0
            else:
                self._value = new_val
            self.valueChanged.emit(self._value)
            self._render_stars()

    def _render_stars(self):
        if self.width() <= 0 or self.height() <= 0:
            return
            
        pm = QPixmap(self.width(), self.height())
        pm.fill(Qt.GlobalColor.transparent)
        
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Fetch theme from parent window if available
            is_dark = getattr(self.window(), '_dark', False)
            disabled = not self.isEnabled()

            if disabled:
                # When no file is loaded the widget is disabled — stars are
                # rendered in the same muted tone as empty stars so the whole
                # widget visually recedes rather than looking interactive.
                active_color   = QColor("#3a3e52" if is_dark else "#d0d0d8")
                inactive_color = QColor("#3a3e52" if is_dark else "#d0d0d8")
                hover_color    = inactive_color
            else:
                active_color   = QColor("#e5a50a" if is_dark else "#f0b429")
                inactive_color = QColor("#3a3e52" if is_dark else "#d0d0d8")
                hover_color    = QColor("#ffca28")

            font = QFont(self.font().family(), 18)
            p.setFont(font)

            w = self.width() / 5.0

            for i in range(1, 6):
                rect = QRect(int((i - 1) * w), 0, int(w), self.height())

                if self._hovering and not disabled:
                    p.setPen(hover_color if i <= self._hover_value else inactive_color)
                else:
                    p.setPen(active_color if i <= self._value else inactive_color)

                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "★")
        finally:
            p.end()
            
        self.setPixmap(pm)

