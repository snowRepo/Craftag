"""
editor_panel.py — Right-hand tag editor (single file + batch).

Single-file layout:
  [110×110 art — centred]
  [Remove]             ← centred below art
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
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QTabWidget, QTextEdit
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QPixmap, QImage

from craftag_py.core.tag_io import AudioTag, save_tag, read_art
from craftag_py.ui.widgets import ArtLabel, HSep, StarRatingWidget


def _px_from_bytes(data: bytes) -> QPixmap:
    img = QImage()
    img.loadFromData(data)
    return QPixmap.fromImage(img)


# ── iTunes lookup worker ────────────────────────────────────────────────────────────

class iTunesWorker(QObject):
    """Runs an iTunes Search API lookup on a background thread.
    Emits exactly one of: found / not_found / error.
    """
    found     = Signal(dict)
    not_found = Signal()
    error     = Signal(str)

    def __init__(self, title: str, artist: str):
        super().__init__()
        self._title  = title
        self._artist = artist

    def run(self):
        try:
            from craftag_py.core.musicbrainz import lookup_recording
            result = lookup_recording(self._title, self._artist)
            if result:
                self.found.emit(result)
            else:
                self.not_found.emit()
        except Exception:
            self.error.emit("Network error. Please check your internet connection and try again.")


# ── Editor panel ───────────────────────────────────────────────────────────────

class EditorPanel(QWidget):
    status_message = Signal(str, bool)
    tags_dirtied = Signal(list)
    tags_renamed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags: List[AudioTag] = []
        self._art_bytes: Optional[bytes] = None
        self._art_mime: Optional[str] = None
        self._art_removed = False
        self._batch_original: dict = {}   # field → common value when batch was loaded
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
        art_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._art = ArtLabel()
        self._art.clicked.connect(self._pick_art)
        self._art.file_dropped.connect(self._load_art_from_path)
        art_row.addWidget(self._art)
        root.addLayout(art_row)
        root.addSpacing(8)

        # ── Art buttons — centred below art ───────────────────────────────
        art_btn_row = QHBoxLayout()
        art_btn_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        art_btn_row.setSpacing(6)

        self._btn_remove_art = QPushButton("Remove")
        self._btn_remove_art.setObjectName("smallDangerBtn")
        self._btn_remove_art.setFixedHeight(22)
        self._btn_remove_art.clicked.connect(self._remove_art)

        art_btn_row.addWidget(self._btn_remove_art)
        root.addLayout(art_btn_row)
        root.addSpacing(4)

        # ── Track meta — centred ───────────────────────────────────────────
        self._lbl_title = QLabel("No file selected")
        self._lbl_title.setObjectName("trackTitle")
        self._lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_title.setWordWrap(True)
        root.addWidget(self._lbl_title)

        self._lbl_artist = QLabel("Select a file from the queue")
        self._lbl_artist.setObjectName("trackArtist")
        self._lbl_artist.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._lbl_artist)

        self._batch_note = QLabel("")
        self._batch_note.setObjectName("batchNote")
        self._batch_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._batch_note.setWordWrap(True)
        root.addWidget(self._batch_note)
        
        rename_layout = QHBoxLayout()
        rename_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._btn_rename = QPushButton("Rename File")
        self._btn_rename.setObjectName("secondary")
        self._btn_rename.setFixedHeight(24)
        self._btn_rename.setFixedWidth(100)
        self._btn_rename.clicked.connect(self._rename_files)
        rename_layout.addWidget(self._btn_rename)
        root.addLayout(rename_layout)
        
        root.addSpacing(6)

        # ── Separator ──────────────────────────────────────────────────────
        root.addWidget(HSep())
        root.addSpacing(8)

        # ── Tabs ───────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setObjectName("editorTabs")
        root.addWidget(self._tabs)
        root.addSpacing(12)

        def field(ph=""):
            e = QLineEdit()
            e.setPlaceholderText(ph)
            e.setFixedHeight(30)
            return e

        def lbl(text):
            lbl_widget = QLabel(text)
            lbl_widget.setObjectName("fieldLabel")
            return lbl_widget
            
        def setup_grid(grid):
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(1)
            grid.setContentsMargins(10, 10, 10, 10)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            return grid

        self._f_title = field("Track title")
        self._f_artist = field("Artist name")
        self._f_album = field("Album name")
        self._f_album_artist = field("Album artist")
        self._f_composer = field("Composer")
        self._f_genre = field("Genre")
        self._f_year = field("YYYY")
        self._f_track = field("e.g. 1")
        self._f_disc = field("e.g. 1")
        self._f_comments = field("Comments")
        
        self._f_bpm = field("BPM (e.g. 120)")
        self._f_rating = StarRatingWidget()
        self._f_rating.setFixedHeight(30)
        self._f_lyrics = QTextEdit()
        self._f_lyrics.setObjectName("lyricsEditor")
        self._f_lyrics.setPlaceholderText("Paste lyrics here...")

        self._f_track_layout = QHBoxLayout()
        self._f_track_layout.setContentsMargins(0, 0, 0, 0)
        self._f_track_layout.addWidget(self._f_track)
        self._btn_auto_track = QPushButton("1..N")
        self._btn_auto_track.setObjectName("smallBtn")
        self._btn_auto_track.setFixedHeight(32)
        self._btn_auto_track.clicked.connect(self._auto_track)
        self._btn_auto_track.hide()
        self._f_track_layout.addWidget(self._btn_auto_track)
        self._f_track_widget = QWidget()
        self._f_track_widget.setLayout(self._f_track_layout)

        # Tab 1: Basic
        basic_w = QWidget()
        basic_grid = setup_grid(QGridLayout(basic_w))
        basic_pairs = [
            ("Title", self._f_title, "Artist", self._f_artist),
            ("Album", self._f_album, "Album Artist", self._f_album_artist),
            ("Genre", self._f_genre, "Year", self._f_year),
            ("Track #", self._f_track_widget, "Disc #", self._f_disc),
        ]
        
        # Tab 2: Advanced
        adv_w = QWidget()
        adv_grid = setup_grid(QGridLayout(adv_w))
        adv_pairs = [
            ("Composer", self._f_composer, "Comments", self._f_comments),
            ("BPM", self._f_bpm, "Rating", self._f_rating),
            (None, None, None, None),
            (None, None, None, None),
        ]
        
        def populate(grid, pairs):
            for r, (l0, f0, l1, f1) in enumerate(pairs):
                base = r * 3
                if l0 is None:
                    # Insert empty label to absorb the same proportional stretch 
                    grid.addWidget(QLabel(""), base, 0)
                else:
                    grid.addWidget(lbl(l0), base, 0)
                    grid.addWidget(lbl(l1), base, 1)
                    grid.addWidget(f0, base + 1, 0)
                    grid.addWidget(f1, base + 1, 1)
                
                if r < len(pairs) - 1:
                    gap = QLabel()
                    gap.setFixedHeight(1)
                    grid.addWidget(gap, base + 2, 0, 1, 2)
                    
        populate(basic_grid, basic_pairs)
        populate(adv_grid, adv_pairs)
        
        # Tab 3: Lyrics
        lyr_w = QWidget()
        lyr_l = QVBoxLayout(lyr_w)
        lyr_l.setContentsMargins(10, 10, 10, 10)
        lyr_l.addWidget(self._f_lyrics)
        
        self._tabs.addTab(basic_w, "Basic")
        self._tabs.addTab(adv_w, "Advanced")
        self._tabs.addTab(lyr_w, "Lyrics")

        # ── Save button ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 0, 12, 0)
        
        self._btn_autofill = QPushButton("Auto-Fill")
        self._btn_autofill.setObjectName("secondary")
        self._btn_autofill.setFixedHeight(34)
        self._btn_autofill.clicked.connect(self._on_autofill)
        btn_row.addWidget(self._btn_autofill)
        

        
        btn_row.addStretch()
        
        self._btn_save = QPushButton("Save Tags", self)
        self._btn_save.setFixedHeight(34)
        self._btn_save.setMinimumWidth(110)
        self._btn_save.clicked.connect(self._save)
        btn_row.addWidget(self._btn_save)
        root.addLayout(btn_row)

        # ── Auto-track dirtiness ───────────────────────────────────────────
        for f in self._all_lineedits():
            f.textEdited.connect(self._mark_dirty)
        self._f_lyrics.textChanged.connect(self._mark_dirty)
        self._f_rating.valueChanged.connect(self._mark_dirty)

        self._set_enabled(False)

    # ── State helpers ──────────────────────────────────────────────────────

    def _mark_dirty(self):
        dirtied = []
        for tag in self._tags:
            if not tag.is_dirty:
                tag.is_dirty = True
                dirtied.append(tag)
        if dirtied:
            self.tags_dirtied.emit(dirtied)

    def _show_empty(self):
        self._lbl_title.setText("No file selected")
        self._lbl_artist.setText("Select a file from the queue")
        self._batch_note.setText("")
        self._art.clear_art()
        for f in self._all_lineedits():
            f.clear()
        self._f_lyrics.clear()
        self._f_rating.clear()
        self._btn_auto_track.hide()
        self._set_enabled(False)

    def _set_enabled(self, on: bool):
        for w in (self._btn_save, self._btn_rename, self._btn_autofill, self._btn_remove_art,
                  *self._all_fields_list()):
            w.setEnabled(on)

    def _all_lineedits(self):
        return [self._f_title, self._f_artist, self._f_album,
                self._f_album_artist, self._f_composer, self._f_genre,
                self._f_year, self._f_track, self._f_disc, self._f_comments,
                self._f_bpm]
                
    def _all_fields_list(self):
        return self._all_lineedits() + [self._f_lyrics]

    # ── Public API ─────────────────────────────────────────────────────────

    def load_single(self, tag: AudioTag):
        self._tags = [tag]
        self._art_bytes = None
        self._art_mime = None
        self._art_removed = False
        self._set_enabled(True)
        self._f_title.setEnabled(True)
        self._batch_note.setText("")
        self._btn_save.setText("Save Tags")
        self._btn_auto_track.hide()

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
        self._f_bpm.setText(tag.bpm or "")
        self._f_lyrics.setText(tag.lyrics or "")
        self._f_rating.setValue(tag.rating)

        self._art.clear_art()
        if tag._staged_art:
            px = _px_from_bytes(tag._staged_art)
            if not px.isNull():
                self._art.set_pixmap(px)
            self._art_bytes = tag._staged_art
            self._art_mime = tag._staged_art_mime
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
        self._art_mime = None
        self._art_removed = False
        self._batch_original = {}
        self._set_enabled(True)
        self._f_title.setEnabled(False)

        n = len(tags)
        self._lbl_title.setText(f"{n} files selected")
        self._lbl_artist.setText("Title is per-file only")
        self._batch_note.setText("")
        self._btn_save.setText(f"Apply to {n} files")
        self._btn_auto_track.show()

        def common(get):
            vals = [get(t) or "" for t in tags]
            return vals[0] if len(set(vals)) == 1 else ""

        fields = {
            "artist":       common(lambda t: t.artist),
            "album":        common(lambda t: t.album),
            "album_artist": common(lambda t: t.album_artist),
            "composer":     common(lambda t: t.composer),
            "genre":        common(lambda t: t.genre),
            "year":         common(lambda t: t.year),
            "disc":         common(lambda t: t.disc),
            "comments":     common(lambda t: t.comments),
            "bpm":          common(lambda t: t.bpm),
        }
        
        def common_lyrics():
            vals = [t.lyrics or "" for t in tags]
            return vals[0] if len(set(vals)) == 1 else ""
            
        def common_rating():
            vals = [t.rating for t in tags]
            return vals[0] if len(set(vals)) == 1 else 0
            
        fields["lyrics"] = common_lyrics()
        fields["rating"] = common_rating()
        self._batch_original = dict(fields)

        self._f_title.setText("(multiple values)")
        self._f_artist.setText(fields["artist"])
        self._f_album.setText(fields["album"])
        self._f_album_artist.setText(fields["album_artist"])
        self._f_composer.setText(fields["composer"])
        self._f_genre.setText(fields["genre"])
        self._f_year.setText(fields["year"])
        self._f_track.setText("")
        self._f_disc.setText(fields["disc"])
        self._f_comments.setText(fields["comments"])
        self._f_bpm.setText(fields["bpm"])
        self._f_lyrics.setText(fields["lyrics"])
        self._f_rating.setValue(fields["rating"])
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
            ext = path.lower().rsplit(".", 1)[-1]
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png", "gif": "image/gif",
                    "bmp": "image/bmp", "webp": "image/webp"}.get(ext, "image/jpeg")
            px = _px_from_bytes(data)
            if not px.isNull():
                self._art.set_pixmap(px)
                self._art_bytes = data
                self._art_mime = mime
                self._art_removed = False
                self._mark_dirty()
        except Exception as e:
            self.status_message.emit(f"Failed to load image: {e}", True)

    def _remove_art(self):
        self._art.clear_art()
        self._art_bytes = None
        self._art_mime = None
        self._art_removed = True
        self._mark_dirty()

    # ── Save & Memory ──────────────────────────────────────────────────────

    def commit_to_memory(self):
        """Applies the current UI state to the `self._tags` models if dirty."""
        if not self._tags:
            return
        if len(self._tags) == 1:
            tag = self._tags[0]
            if not tag.is_dirty: return
            tag.title = self._f_title.text().strip() or None
            tag.artist = self._f_artist.text().strip() or None
            tag.album = self._f_album.text().strip() or None
            tag.album_artist = self._f_album_artist.text().strip() or None
            tag.composer = self._f_composer.text().strip() or None
            tag.genre = self._f_genre.text().strip() or None
            tag.year = self._f_year.text().strip() or None
            tag.track = self._f_track.text().strip() or None
            tag.disc = self._f_disc.text().strip() or None
            tag.comments = self._f_comments.text().strip() or None
            tag.bpm = self._f_bpm.text().strip() or None
            tag.lyrics = self._f_lyrics.toPlainText().strip() or None
            tag.rating = self._f_rating.value()
            tag._staged_art = self._art_bytes
            tag._staged_art_mime = self._art_mime
            tag._staged_art_removed = self._art_removed
        else:
            # Check if batch is actually dirty
            any_dirty = any(t.is_dirty for t in self._tags)
            if not any_dirty: return

            def resolve(ui_text: str, original: str) -> tuple[bool, Optional[str]]:
                v = ui_text.strip()
                if v:
                    return True, v
                if original:
                    return True, None
                return False, None
                
            def resolve_rating(ui_val: int, original: int) -> tuple[bool, int]:
                if ui_val != original:
                    return True, ui_val
                return False, ui_val

            orig = self._batch_original
            fields = [
                ("artist",       self._f_artist.text(),       orig.get("artist",       "")),
                ("album",        self._f_album.text(),        orig.get("album",        "")),
                ("album_artist", self._f_album_artist.text(), orig.get("album_artist", "")),
                ("composer",     self._f_composer.text(),     orig.get("composer",     "")),
                ("genre",        self._f_genre.text(),        orig.get("genre",        "")),
                ("year",         self._f_year.text(),         orig.get("year",         "")),
                ("disc",         self._f_disc.text(),         orig.get("disc",         "")),
                ("comments",     self._f_comments.text(),     orig.get("comments",     "")),
                ("bpm",          self._f_bpm.text(),          orig.get("bpm",          "")),
                ("lyrics",       self._f_lyrics.toPlainText(),orig.get("lyrics",       "")),
            ]
            
            ui_rating = self._f_rating.value()
            orig_rating = orig.get("rating", 0)

            for tag in self._tags:
                for attr, ui_val, orig_val in fields:
                    should_write, new_val = resolve(ui_val, orig_val)
                    if should_write:
                        setattr(tag, attr, new_val)
                should_write_rating, new_rating = resolve_rating(ui_rating, orig_rating)
                if should_write_rating:
                    tag.rating = new_rating
                if self._art_bytes:
                    tag._staged_art = self._art_bytes
                    tag._staged_art_mime = self._art_mime
                    tag._staged_art_removed = False
                elif self._art_removed:
                    tag._staged_art_removed = True

    def _save(self):
        """Called by the Save button. Commits to memory, then writes active tags to disk."""
        if not self._tags:
            return
        self.commit_to_memory()
        
        ok = fail = 0
        for tag in self._tags:
            try:
                save_tag(tag)
                tag.is_dirty = False
                tag._staged_art = tag._staged_art_mime = None
                tag._staged_art_removed = False
                tag.has_art = (self._art_bytes is not None) or (
                    tag.has_art and not self._art_removed
                )
                ok += 1
            except Exception as e:
                print(f"[editor save] {tag.path}: {e}")
                fail += 1

        if len(self._tags) == 1:
            tag = self._tags[0]
            self._lbl_title.setText(tag.title or tag.filename)
            self._lbl_artist.setText(tag.artist or "Unknown Artist")

        if fail == 0:
            if len(self._tags) > 1:
                self.status_message.emit(f"Saved {ok} files.", False)
            else:
                self.status_message.emit("Tags saved.", False)
            self._show_save_success()
            self.tags_dirtied.emit(self._tags)  # re-emit so FileList removes the ●
        else:
            self.status_message.emit(f"{ok} saved, {fail} failed.", True)

    def _show_save_success(self):
        original_text = self._btn_save.text()
        # ◉ (U+25C9 FISHEYE) — premium filled-circle indicator; no color
        # override so the button keeps its original themed appearance.
        self._btn_save.setText("◉  Saved")

        def reset():
            self._btn_save.setText(original_text)
            self._btn_save.setStyleSheet("")

        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, reset)

    def _auto_track(self):
        """Number selected files sequentially."""
        if len(self._tags) < 2: return
        n = len(self._tags)
        for i, tag in enumerate(self._tags, 1):
            tag.track = f"{i}/{n}"
            tag.is_dirty = True
        self._f_track.setText(f"(numbered 1 to {n})")
        self.tags_dirtied.emit(self._tags)
        self.status_message.emit("Auto-numbered tracks.", False)

    def _rename_files(self):
        if not self._tags: return
        self.commit_to_memory()
        
        import os
        import re
        from PySide6.QtWidgets import QMessageBox
        
        renamed = []
        ok = fail = 0
        
        for tag in self._tags:
            parts = []
            if tag.track:
                t = tag.track.split('/')[0]
                parts.append(t.zfill(2) if t.isdigit() else t)
            if tag.artist:
                parts.append(tag.artist)
            if tag.title:
                parts.append(tag.title)
            
            if not parts:
                parts.append("Unknown Audio")
                
            new_name = " - ".join(parts)
            new_name = re.sub(r'[<>:"/\\|?*]', '_', new_name).strip()
            
            ext = os.path.splitext(tag.path)[1]
            new_path = os.path.join(os.path.dirname(tag.path), new_name + ext)
            
            if new_path == tag.path:
                ok += 1
                continue
                
            if os.path.exists(new_path):
                QMessageBox.warning(
                    self, "Rename Collision",
                    f"Cannot rename to '{new_name + ext}' because a file with that name already exists in the same folder."
                )
                fail += 1
                continue
                
            try:
                os.rename(tag.path, new_path)
                old_path = tag.path
                tag.path = new_path
                tag.filename = new_name + ext
                renamed.append((old_path, tag))
                ok += 1
            except Exception as e:
                self.status_message.emit(f"Rename failed: {e}", True)
                fail += 1
                
        if renamed:
            self.tags_renamed.emit(renamed)
            
        if fail == 0 and ok > 0:
            self.status_message.emit(f"Renamed {ok} file(s).", False)
        elif fail > 0:
            self.status_message.emit(f"Renamed {ok} file(s), {fail} failed.", True)

    # ── Auto-Fill (iTunes) ────────────────────────────────────────────

    def _on_autofill(self):
        """Launch a background iTunes lookup for the current track."""
        if not self._tags:
            return

        title  = self._f_title.text().strip()  or (self._tags[0].title  or "")
        artist = self._f_artist.text().strip() or (self._tags[0].artist or "")

        if not title:
            self.status_message.emit("Enter a title before using Auto-Fill.", True)
            return

        self._btn_autofill.setEnabled(False)
        self._btn_autofill.setText("Looking up…")

        thread = QThread(self)
        worker = iTunesWorker(title, artist)
        worker.moveToThread(thread)

        # Keep strong references so GC doesn't collect them mid-lookup
        if not hasattr(self, "_mb_workers"):
            self._mb_workers: list = []
        self._mb_workers.append((thread, worker))

        thread.started.connect(worker.run)

        def _done():
            if (thread, worker) in self._mb_workers:
                self._mb_workers.remove((thread, worker))
            worker.deleteLater()
            thread.deleteLater()

        worker.found.connect(self._on_autofill_found)
        worker.not_found.connect(self._on_autofill_not_found)
        worker.error.connect(self._on_autofill_error)
        for sig in (worker.found, worker.not_found, worker.error):
            sig.connect(thread.quit)
        thread.finished.connect(_done)

        thread.start()

    def _on_autofill_found(self, data: dict):
        self._btn_autofill.setText("Auto-Fill")
        self._btn_autofill.setEnabled(True)

        field_map = [
            ("artist",       self._f_artist),
            ("album",        self._f_album),
            ("album_artist", self._f_album_artist),
            ("year",         self._f_year),
            ("track",        self._f_track),
            ("genre",        self._f_genre),
        ]
        filled = []
        for key, widget in field_map:
            if not widget.text().strip() and data.get(key):
                widget.setText(data[key])
                filled.append(key)

        if filled:
            self._mark_dirty()
            self.status_message.emit(
                f"Auto-Fill: filled {len(filled)} field(s) from iTunes.", False
            )
        else:
            self.status_message.emit("Auto-Fill: all fields already filled.", False)

    def _on_autofill_not_found(self):
        self._btn_autofill.setText("Auto-Fill")
        self._btn_autofill.setEnabled(True)
        self.status_message.emit("Auto-Fill: no match found on iTunes.", True)

    def _on_autofill_error(self, msg: str):
        self._btn_autofill.setText("Auto-Fill")
        self._btn_autofill.setEnabled(True)
        self.status_message.emit(f"Auto-Fill error: {msg}", True)
