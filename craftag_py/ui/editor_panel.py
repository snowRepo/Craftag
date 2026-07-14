"""
editor_panel.py — Right-hand tag editor (single file + batch).

Single-file layout:
  [110×110 art — centred]
  [Set Art…]  [Remove]       ← centred below art
  Track Title (centred)
  Artist (centred)
  ─────────────────────────
  Title      │ Artist
  Album      │ Album Artist
  Composer   │ Genre
  Year       │ Track #
  Disc #     │ Comments
  ─────────────────────────
                  [Save Tags]
"""
from __future__ import annotations
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage

from craftag_py.core.tag_io import AudioTag, save_tag, read_art
from craftag_py.ui.widgets import ArtLabel, HSep


def _px_from_bytes(data: bytes) -> QPixmap:
    img = QImage()
    img.loadFromData(data)
    return QPixmap.fromImage(img)


class EditorPanel(QWidget):
    status_message = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags: List[AudioTag] = []
        self._art_bytes: Optional[bytes] = None
        self._art_mime:  Optional[str]   = None
        self._art_removed = False
        self._build_ui()
        self._show_empty()

    # ── Theme passthrough ──────────────────────────────────────────────────

    def set_dark(self, dark: bool):
        self._art.set_dark(dark)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 14)
        root.setSpacing(0)

        # ── Album art — centred ────────────────────────────────────────────
        art_row = QHBoxLayout()
        art_row.setAlignment(Qt.AlignHCenter)
        self._art = ArtLabel()
        self._art.clicked.connect(self._pick_art)
        self._art.file_dropped.connect(self._load_art_from_path)
        art_row.addWidget(self._art)
        root.addLayout(art_row)
        root.addSpacing(8)

        # ── Art buttons — centred below art ───────────────────────────────
        art_btn_row = QHBoxLayout()
        art_btn_row.setAlignment(Qt.AlignHCenter)
        art_btn_row.setSpacing(6)

        self._btn_set_art = QPushButton("Set Art…")
        self._btn_set_art.setObjectName("smallBtn")
        self._btn_set_art.setFixedHeight(22)
        self._btn_set_art.clicked.connect(self._pick_art)

        self._btn_remove_art = QPushButton("Remove")
        self._btn_remove_art.setObjectName("smallDangerBtn")
        self._btn_remove_art.setFixedHeight(22)
        self._btn_remove_art.clicked.connect(self._remove_art)

        art_btn_row.addWidget(self._btn_set_art)
        art_btn_row.addWidget(self._btn_remove_art)
        root.addLayout(art_btn_row)
        root.addSpacing(10)

        # ── Track meta — centred ───────────────────────────────────────────
        self._lbl_title = QLabel("No file selected")
        self._lbl_title.setObjectName("trackTitle")
        self._lbl_title.setAlignment(Qt.AlignCenter)
        self._lbl_title.setWordWrap(True)
        root.addWidget(self._lbl_title)

        self._lbl_artist = QLabel("Select a file from the queue")
        self._lbl_artist.setObjectName("trackArtist")
        self._lbl_artist.setAlignment(Qt.AlignCenter)
        root.addWidget(self._lbl_artist)

        self._batch_note = QLabel("")
        self._batch_note.setObjectName("batchNote")
        self._batch_note.setAlignment(Qt.AlignCenter)
        self._batch_note.setWordWrap(True)
        root.addWidget(self._batch_note)
        root.addSpacing(10)

        # ── Separator ──────────────────────────────────────────────────────
        root.addWidget(HSep())
        root.addSpacing(10)

        # ── 2-column field grid — no full-width spans ──────────────────────
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def field(ph=""):
            e = QLineEdit()
            e.setPlaceholderText(ph)
            e.setFixedHeight(28)
            return e

        def lbl(text):
            l = QLabel(text)
            l.setObjectName("fieldLabel")
            return l

        self._f_title        = field("Track title")
        self._f_artist       = field("Artist name")
        self._f_album        = field("Album name")
        self._f_album_artist = field("Album artist")
        self._f_composer     = field("Composer")
        self._f_genre        = field("Genre")
        self._f_year         = field("YYYY")
        self._f_track        = field("e.g. 1")
        self._f_disc         = field("e.g. 1")
        self._f_comments     = field("Comments")

        pairs = [
            ("Title",    self._f_title,    "Artist",       self._f_artist),
            ("Album",    self._f_album,    "Album Artist", self._f_album_artist),
            ("Composer", self._f_composer, "Genre",        self._f_genre),
            ("Year",     self._f_year,     "Track #",      self._f_track),
            ("Disc #",   self._f_disc,     "Comments",     self._f_comments),
        ]

        for r, (l0, f0, l1, f1) in enumerate(pairs):
            base = r * 3
            grid.addWidget(lbl(l0), base,     0)
            grid.addWidget(lbl(l1), base,     1)
            grid.addWidget(f0,      base + 1, 0)
            grid.addWidget(f1,      base + 1, 1)
            if r < len(pairs) - 1:
                gap = QLabel()
                gap.setFixedHeight(3)
                grid.addWidget(gap, base + 2, 0, 1, 2)

        root.addLayout(grid)
        root.addSpacing(12)

        # ── Save button ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_save = QPushButton("Save Tags")
        self._btn_save.setObjectName("primary")
        self._btn_save.setFixedHeight(34)
        self._btn_save.setMinimumWidth(110)
        self._btn_save.clicked.connect(self._save)
        btn_row.addWidget(self._btn_save)
        root.addLayout(btn_row)

        self._set_enabled(False)

    # ── State helpers ──────────────────────────────────────────────────────

    def _show_empty(self):
        self._lbl_title.setText("No file selected")
        self._lbl_artist.setText("Select a file from the queue")
        self._batch_note.setText("")
        self._art.clear_art()
        for f in self._all_fields():
            f.clear()
        self._set_enabled(False)

    def _set_enabled(self, on: bool):
        for w in (self._btn_save, self._btn_set_art, self._btn_remove_art,
                  *self._all_fields()):
            w.setEnabled(on)

    def _all_fields(self):
        return [self._f_title, self._f_artist, self._f_album,
                self._f_album_artist, self._f_composer, self._f_genre,
                self._f_year, self._f_track, self._f_disc, self._f_comments]

    # ── Public API ─────────────────────────────────────────────────────────

    def load_single(self, tag: AudioTag):
        self._tags = [tag]
        self._art_bytes = None
        self._art_mime  = None
        self._art_removed = False
        self._set_enabled(True)
        self._f_title.setEnabled(True)
        self._batch_note.setText("")
        self._btn_save.setText("Save Tags")

        self._lbl_title.setText(tag.title or tag.filename)
        self._lbl_artist.setText(tag.artist or "Unknown Artist")

        self._f_title.setText(tag.title or "")
        self._f_artist.setText(tag.artist or "")
        self._f_album.setText(tag.album or "")
        self._f_album_artist.setText(tag.album_artist or "")
        self._f_composer.setText(tag.composer or "")
        self._f_genre.setText(tag.genre or "")
        self._f_year.setText(tag.year or "")
        self._f_track.setText(tag.track or "")
        self._f_disc.setText(tag.disc or "")
        self._f_comments.setText(tag.comments or "")

        self._art.clear_art()
        if tag._staged_art:
            px = _px_from_bytes(tag._staged_art)
            if not px.isNull():
                self._art.set_pixmap(px)
            self._art_bytes = tag._staged_art
            self._art_mime  = tag._staged_art_mime
        elif tag._staged_art_removed:
            self._art_removed = True
        elif tag.has_art:
            result = read_art(tag.path)
            if result:
                data, mime = result
                px = _px_from_bytes(data)
                if not px.isNull():
                    self._art.set_pixmap(px)

    def load_batch(self, tags: List[AudioTag]):
        self._tags = tags
        self._art_bytes = None
        self._art_mime  = None
        self._art_removed = False
        self._set_enabled(True)
        self._f_title.setEnabled(False)

        n = len(tags)
        self._lbl_title.setText(f"{n} files selected")
        self._lbl_artist.setText("Shared fields — blank = keep existing")
        self._batch_note.setText("⚠ Batch: title is per-file only.")
        self._btn_save.setText(f"Apply to {n} files")

        def common(get):
            vals = [get(t) or "" for t in tags]
            return vals[0] if len(set(vals)) == 1 else ""

        self._f_title.setText("(multiple values)")
        self._f_artist.setText(common(lambda t: t.artist))
        self._f_album.setText(common(lambda t: t.album))
        self._f_album_artist.setText(common(lambda t: t.album_artist))
        self._f_composer.setText(common(lambda t: t.composer))
        self._f_genre.setText(common(lambda t: t.genre))
        self._f_year.setText(common(lambda t: t.year))
        self._f_track.setText("")
        self._f_disc.setText(common(lambda t: t.disc))
        self._f_comments.setText(common(lambda t: t.comments))
        self._art.clear_art()

    def clear(self):
        self._tags = []
        self._show_empty()

    # ── Art ────────────────────────────────────────────────────────────────

    def _pick_art(self):
        if not self._tags:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Album Art", "",
            "Images (*.jpg *.jpeg *.png *.gif *.bmp *.webp)"
        )
        if path:
            self._load_art_from_path(path)

    def _load_art_from_path(self, path: str):
        try:
            with open(path, "rb") as f:
                data = f.read()
            ext  = path.lower().rsplit(".", 1)[-1]
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png",  "gif":  "image/gif",
                    "bmp": "image/bmp",  "webp": "image/webp"}.get(ext, "image/jpeg")
            px = _px_from_bytes(data)
            if not px.isNull():
                self._art.set_pixmap(px)
                self._art_bytes   = data
                self._art_mime    = mime
                self._art_removed = False
        except Exception as e:
            self.status_message.emit(f"Failed to load image: {e}", True)

    def _remove_art(self):
        self._art.clear_art()
        self._art_bytes   = None
        self._art_mime    = None
        self._art_removed = True

    # ── Save ───────────────────────────────────────────────────────────────

    def _save(self):
        if not self._tags:
            return
        if len(self._tags) == 1:
            self._save_single()
        else:
            self._save_batch()

    def _save_single(self):
        tag = self._tags[0]
        tag.title        = self._f_title.text().strip() or None
        tag.artist       = self._f_artist.text().strip() or None
        tag.album        = self._f_album.text().strip() or None
        tag.album_artist = self._f_album_artist.text().strip() or None
        tag.composer     = self._f_composer.text().strip() or None
        tag.genre        = self._f_genre.text().strip() or None
        tag.year         = self._f_year.text().strip() or None
        tag.track        = self._f_track.text().strip() or None
        tag.disc         = self._f_disc.text().strip() or None
        tag.comments     = self._f_comments.text().strip() or None
        tag._staged_art         = self._art_bytes
        tag._staged_art_mime    = self._art_mime
        tag._staged_art_removed = self._art_removed
        try:
            save_tag(tag)
            tag._staged_art = tag._staged_art_mime = None
            tag._staged_art_removed = False
            tag.has_art = (self._art_bytes is not None) or (
                tag.has_art and not self._art_removed
            )
            self._lbl_title.setText(tag.title or tag.filename)
            self._lbl_artist.setText(tag.artist or "Unknown Artist")
            self.status_message.emit("Tags saved.", False)
        except Exception as e:
            self.status_message.emit(f"Save failed: {e}", True)

    def _save_batch(self):
        artist       = self._f_artist.text().strip() or None
        album        = self._f_album.text().strip() or None
        album_artist = self._f_album_artist.text().strip() or None
        composer     = self._f_composer.text().strip() or None
        genre        = self._f_genre.text().strip() or None
        year         = self._f_year.text().strip() or None
        disc         = self._f_disc.text().strip() or None
        comments     = self._f_comments.text().strip() or None

        ok = fail = 0
        for tag in self._tags:
            if artist:       tag.artist       = artist
            if album:        tag.album        = album
            if album_artist: tag.album_artist = album_artist
            if composer:     tag.composer     = composer
            if genre:        tag.genre        = genre
            if year:         tag.year         = year
            if disc:         tag.disc         = disc
            if comments:     tag.comments     = comments
            if self._art_bytes:
                tag._staged_art         = self._art_bytes
                tag._staged_art_mime    = self._art_mime
                tag._staged_art_removed = False
            elif self._art_removed:
                tag._staged_art_removed = True
            try:
                save_tag(tag)
                tag._staged_art = tag._staged_art_mime = None
                tag._staged_art_removed = False
                ok += 1
            except Exception as e:
                print(f"[batch save] {tag.path}: {e}")
                fail += 1

        if fail == 0:
            self.status_message.emit(f"Saved {ok} files.", False)
        else:
            self.status_message.emit(f"{ok} saved, {fail} failed.", True)
