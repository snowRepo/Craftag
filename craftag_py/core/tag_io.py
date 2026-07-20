"""
tag_io.py — Craftag core I/O layer using mutagen.

All tag reading and writing goes through this module.
mutagen is format-agnostic and handles ID3v2.3/2.4, FLAC, MP4,
OGG, OPUS, WMA, WAV, AIFF — identically on every OS.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import mutagen
from mutagen.id3 import (
    ID3, ID3NoHeaderError,
    TIT2, TPE1, TALB, TPE2, TCOM, TCON, TDRC, TRCK, TPOS, COMM,
    APIC, TBPM, USLT, POPM,
)
from mutagen.flac import FLAC, Picture as FLACPicture
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.wavpack import WavPack
from mutagen.apev2 import APEv2, APETextValue
from mutagen.wave import WAVE
from mutagen.aiff import AIFF

# Audio file extensions we support
SUPPORTED_EXTENSIONS = {
    ".mp3", ".flac", ".ogg", ".opus",
    ".m4a", ".aac", ".mp4",
    ".wav", ".aif", ".aiff",
    ".wv",
}


@dataclass
class AudioTag:
    """Flat, format-agnostic representation of an audio file's metadata."""
    path: str
    filename: str
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    composer: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[str] = None
    track: Optional[str] = None
    disc: Optional[str] = None
    comments: Optional[str] = None
    bpm: Optional[str] = None
    lyrics: Optional[str] = None
    rating: int = 0
    has_art: bool = False
    is_dirty: bool = False
    # In-memory staged art (bytes) — not persisted until save()
    _staged_art: Optional[bytes] = field(default=None, repr=False)
    _staged_art_mime: Optional[str] = field(default=None, repr=False)
    _staged_art_removed: bool = field(default=False, repr=False)

    def copy(self) -> "AudioTag":
        import copy
        return copy.copy(self)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _str(v) -> Optional[str]:
    """Safely convert a mutagen value to a clean string."""
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _popm_to_stars(val: int) -> int:
    """Convert an ID3 POPM value (0-255) to a 0-5 star rating."""
    if not val: return 0
    if val >= 200: return 5
    if val >= 150: return 4
    if val >= 100: return 3
    if val >= 50: return 2
    return 1

def _stars_to_popm(val: int) -> int:
    """Convert a 0-5 star rating to an ID3 POPM value (0-255).
    Follows Windows Explorer standard mapping."""
    m = {0: 0, 1: 1, 2: 64, 3: 128, 4: 196, 5: 255}
    return m.get(val, 0)


def _norm_path(path: str) -> str:
    """Return a normalised path: resolves `.`, `..`, double slashes, and
    trailing separators.  Works identically on Windows, macOS, and Linux.
    The display casing of the original path is preserved (normcase is
    applied only at comparison time in file_list.py)."""
    return os.path.normpath(path)


def _ext(path: str) -> str:
    return Path(path).suffix.lower()


# ── Readers ──────────────────────────────────────────────────────────────────

def _read_id3(path: str) -> AudioTag:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = {}

    has_art = bool(tags.get("APIC:") or tags.get("APIC"))
    if not has_art:
        # Check all APIC frames
        has_art = any(k.startswith("APIC") for k in tags.keys())

    def get(key):
        frame = tags.get(key)
        return _str(frame.text[0]) if frame and hasattr(frame, "text") else None

    def get_comm():
        for k, v in tags.items():
            if k.startswith("COMM"):
                return _str(v.text[0]) if v.text else None
        return None

    def get_lyrics():
        for k, v in tags.items():
            if k.startswith("USLT"):
                return _str(v.text)
        return None

    def get_rating():
        for k, v in tags.items():
            if k.startswith("POPM"):
                return _popm_to_stars(v.rating)
        return 0

    return AudioTag(
        path=path,
        filename=os.path.basename(path),
        title=get("TIT2"),
        artist=get("TPE1"),
        album=get("TALB"),
        album_artist=get("TPE2"),
        composer=get("TCOM"),
        genre=get("TCON"),
        year=get("TDRC"),
        track=get("TRCK"),
        disc=get("TPOS"),
        comments=get_comm(),
        bpm=get("TBPM"),
        lyrics=get_lyrics(),
        rating=get_rating(),
        has_art=has_art,
    )


def _read_flac(path: str) -> AudioTag:
    audio = FLAC(path)
    tags = audio.tags or {}

    def get(key):
        vals = tags.get(key.lower()) or tags.get(key.upper())
        return _str(vals[0]) if vals else None

    return AudioTag(
        path=path,
        filename=os.path.basename(path),
        title=get("title"),
        artist=get("artist"),
        album=get("album"),
        album_artist=get("albumartist"),
        composer=get("composer"),
        genre=get("genre"),
        year=get("date"),
        track=get("tracknumber"),
        disc=get("discnumber"),
        comments=get("comment"),
        bpm=get("bpm"),
        lyrics=get("lyrics") or get("unsyncedlyrics"),
        rating=int(get("rating") or 0) if str(get("rating") or "").isdigit() else 0,
        has_art=bool(audio.pictures),
    )


def _read_mp4(path: str) -> AudioTag:
    audio = MP4(path)
    tags = audio.tags or {}

    def get(key):
        vals = tags.get(key)
        if not vals:
            return None
        v = vals[0]
        if isinstance(v, tuple):
            return _str(v[0])
        return _str(v)

    def get_track():
        vals = tags.get("trkn")
        if vals:
            t = vals[0]
            if isinstance(t, tuple):
                return str(t[0]) if t[0] else None
        return None

    def get_disc():
        vals = tags.get("disk")
        if vals:
            d = vals[0]
            if isinstance(d, tuple):
                return str(d[0]) if d[0] else None
        return None

    def get_bpm():
        vals = tags.get("tmpo")
        if vals:
            t = vals[0]
            if isinstance(t, tuple) or isinstance(t, int):
                return str(t) if isinstance(t, int) else str(t[0])
        return None

    return AudioTag(
        path=path,
        filename=os.path.basename(path),
        title=get("\xa9nam"),
        artist=get("\xa9ART"),
        album=get("\xa9alb"),
        album_artist=get("aART"),
        composer=get("\xa9wrt"),
        genre=get("\xa9gen"),
        year=get("\xa9day"),
        track=get_track(),
        disc=get_disc(),
        comments=get("\xa9cmt"),
        bpm=get_bpm(),
        lyrics=get("\xa9lyr"),
        rating=int(get("rate") or 0) if str(get("rate") or "").isdigit() else 0,
        has_art=bool(tags.get("covr")),
    )


def _read_vorbis(path: str, cls) -> AudioTag:
    audio = cls(path)
    tags = audio.tags or {}

    def get(key):
        vals = tags.get(key.lower()) or tags.get(key.upper())
        return _str(vals[0]) if vals else None

    has_art = any(
        k.lower() in ("metadata_block_picture", "coverart")
        for k in tags.keys()
    )

    return AudioTag(
        path=path,
        filename=os.path.basename(path),
        title=get("title"),
        artist=get("artist"),
        album=get("album"),
        album_artist=get("albumartist"),
        composer=get("composer"),
        genre=get("genre"),
        year=get("date"),
        track=get("tracknumber"),
        disc=get("discnumber"),
        comments=get("comment"),
        bpm=get("bpm"),
        lyrics=get("lyrics") or get("unsyncedlyrics"),
        rating=int(get("rating") or 0) if str(get("rating") or "").isdigit() else 0,
        has_art=has_art,
    )


_FORMAT_READERS = {
    ".mp3": _read_id3,
    ".wav": _read_id3,
    ".aif": _read_id3,
    ".aiff": _read_id3,
    ".flac": _read_flac,
    ".m4a": _read_mp4,
    ".aac": _read_mp4,
    ".mp4": _read_mp4,
    ".ogg": lambda p: _read_vorbis(p, OggVorbis),
    ".opus": lambda p: _read_vorbis(p, OggOpus),
}


def read_tag(path: str) -> Optional[AudioTag]:
    """Read tags from any supported audio file. Returns None on failure."""
    path = _norm_path(path)   # normalise once; stored path is always clean
    ext = _ext(path)
    reader = _FORMAT_READERS.get(ext)
    if reader is None:
        return None
    try:
        return reader(path)
    except Exception as e:
        print(f"[tag_io] read error {path}: {e}")
        return None


def read_folder(folder: str) -> list[AudioTag]:
    """Recursively walk folder and read all supported audio files."""
    folder = _norm_path(folder)
    results = []
    for root, _, files in os.walk(folder):
        for fname in sorted(files):
            ext = Path(fname).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                tag = read_tag(os.path.join(root, fname))
                if tag:
                    results.append(tag)
    return results


# ── Art reading ───────────────────────────────────────────────────────────────

def read_art(path: str) -> Optional[tuple[bytes, str]]:
    """Return (image_bytes, mime_type) for the first embedded picture, or None."""
    ext = _ext(path)
    try:
        if ext in (".mp3", ".wav", ".aif", ".aiff"):
            tags = ID3(path)
            for k, v in tags.items():
                if k.startswith("APIC"):
                    return v.data, v.mime
        elif ext == ".flac":
            audio = FLAC(path)
            if audio.pictures:
                p = audio.pictures[0]
                return p.data, p.mime
        elif ext in (".m4a", ".aac", ".mp4"):
            audio = MP4(path)
            covers = (audio.tags or {}).get("covr")
            if covers:
                cover = covers[0]
                mime = "image/jpeg" if cover.imageformat == MP4Cover.FORMAT_JPEG else "image/png"
                return bytes(cover), mime
        elif ext in (".ogg", ".opus"):
            audio = (OggVorbis if ext == ".ogg" else OggOpus)(path)
            tags = audio.tags or {}
            for k, v in tags.items():
                if k.lower() == "metadata_block_picture":
                    raw = base64.b64decode(v[0])
                    pic = FLACPicture(raw)
                    return pic.data, pic.mime
    except Exception as e:
        print(f"[tag_io] art read error {path}: {e}")
    return None


# ── Writers ───────────────────────────────────────────────────────────────────

def _write_id3(tag: AudioTag):
    try:
        tags = ID3(tag.path)
    except ID3NoHeaderError:
        tags = ID3()

    def set_text(cls, key, val):
        if val:
            tags[key] = cls(encoding=3, text=[val])
        elif key in tags:
            del tags[key]

    set_text(TIT2, "TIT2", tag.title)
    set_text(TPE1, "TPE1", tag.artist)
    set_text(TALB, "TALB", tag.album)
    set_text(TPE2, "TPE2", tag.album_artist)
    set_text(TCOM, "TCOM", tag.composer)
    set_text(TCON, "TCON", tag.genre)
    set_text(TDRC, "TDRC", tag.year)
    set_text(TRCK, "TRCK", tag.track)
    set_text(TPOS, "TPOS", tag.disc)
    set_text(TBPM, "TBPM", tag.bpm)

    # Comments
    for k in list(tags.keys()):
        if k.startswith("COMM"):
            del tags[k]
    if tag.comments:
        tags["COMM::eng"] = COMM(encoding=3, lang="eng", desc="", text=[tag.comments])

    # Lyrics
    for k in list(tags.keys()):
        if k.startswith("USLT"):
            del tags[k]
    if tag.lyrics:
        tags["USLT::eng"] = USLT(encoding=3, lang="eng", desc="", text=tag.lyrics)

    # Rating
    for k in list(tags.keys()):
        if k.startswith("POPM"):
            del tags[k]
    if tag.rating > 0:
        val = _stars_to_popm(tag.rating)
        tags["POPM:Craftag"] = POPM(email="Craftag", rating=val)

    # Art
    if tag._staged_art_removed:
        for k in list(tags.keys()):
            if k.startswith("APIC"):
                del tags[k]
    elif tag._staged_art:
        for k in list(tags.keys()):
            if k.startswith("APIC"):
                del tags[k]
        tags["APIC:"] = APIC(
            encoding=3,
            mime=tag._staged_art_mime or "image/jpeg",
            type=3,  # Cover front
            desc="",
            data=tag._staged_art,
        )

    # Always save as ID3v2.3 for maximum compatibility.
    # Rationale:
    #   - Windows Media Player (all versions) requires ID3v2.3
    #   - iTunes / Apple Music had longstanding issues with ID3v2.4
    #   - Most hardware players (car stereos, portables) support only v2.3
    #   - v2.4 offers little practical benefit for the tags we expose
    # DO NOT change this to v2_version=4 — it will break WMP on Windows.
    tags.save(tag.path, v2_version=3)


def _write_flac(tag: AudioTag):
    audio = FLAC(tag.path)
    if audio.tags is None:
        audio.add_tags()
    t = audio.tags

    def set_tag(key, val):
        if val:
            t[key] = [val]
        elif key in t:
            del t[key]

    set_tag("title", tag.title)
    set_tag("artist", tag.artist)
    set_tag("album", tag.album)
    set_tag("albumartist", tag.album_artist)
    set_tag("composer", tag.composer)
    set_tag("genre", tag.genre)
    set_tag("date", tag.year)
    set_tag("tracknumber", tag.track)
    set_tag("discnumber", tag.disc)
    set_tag("comment", tag.comments)
    set_tag("bpm", tag.bpm)
    set_tag("lyrics", tag.lyrics)
    set_tag("rating", str(tag.rating) if tag.rating > 0 else None)

    # Art
    if tag._staged_art_removed:
        audio.clear_pictures()
    elif tag._staged_art:
        audio.clear_pictures()
        pic = FLACPicture()
        pic.type = 3
        pic.mime = tag._staged_art_mime or "image/jpeg"
        pic.desc = ""
        pic.data = tag._staged_art
        audio.add_picture(pic)

    audio.save()


def _write_mp4(tag: AudioTag):
    audio = MP4(tag.path)
    if audio.tags is None:
        audio.add_tags()
    t = audio.tags

    def set_tag(key, val):
        if val:
            t[key] = [val]
        elif key in t:
            del t[key]

    set_tag("\xa9nam", tag.title)
    set_tag("\xa9ART", tag.artist)
    set_tag("\xa9alb", tag.album)
    set_tag("aART", tag.album_artist)
    set_tag("\xa9wrt", tag.composer)
    set_tag("\xa9gen", tag.genre)
    set_tag("\xa9day", tag.year)
    set_tag("\xa9cmt", tag.comments)
    set_tag("\xa9lyr", tag.lyrics)
    set_tag("rate", str(tag.rating) if tag.rating > 0 else None)

    if tag.bpm:
        try:
            t["tmpo"] = [int(tag.bpm)]
        except ValueError:
            pass
    elif "tmpo" in t:
        del t["tmpo"]

    # Track & disc need tuple format
    if tag.track:
        try:
            n = int(tag.track.split("/")[0])
            t["trkn"] = [(n, 0)]
        except Exception:
            pass
    elif "trkn" in t:
        del t["trkn"]

    if tag.disc:
        try:
            n = int(tag.disc.split("/")[0])
            t["disk"] = [(n, 0)]
        except Exception:
            pass
    elif "disk" in t:
        del t["disk"]

    # Art
    if tag._staged_art_removed:
        if "covr" in t:
            del t["covr"]
    elif tag._staged_art:
        fmt = MP4Cover.FORMAT_PNG if (tag._staged_art_mime or "").endswith("png") else MP4Cover.FORMAT_JPEG
        t["covr"] = [MP4Cover(tag._staged_art, imageformat=fmt)]

    audio.save()


def _write_vorbis(tag: AudioTag, cls):
    audio = cls(tag.path)
    if audio.tags is None:
        audio.add_tags()
    t = audio.tags

    def set_tag(key, val):
        if val:
            t[key] = [val]
        elif key in t:
            del t[key]

    set_tag("title", tag.title)
    set_tag("artist", tag.artist)
    set_tag("album", tag.album)
    set_tag("albumartist", tag.album_artist)
    set_tag("composer", tag.composer)
    set_tag("genre", tag.genre)
    set_tag("date", tag.year)
    set_tag("tracknumber", tag.track)
    set_tag("discnumber", tag.disc)
    set_tag("comment", tag.comments)
    set_tag("bpm", tag.bpm)
    set_tag("lyrics", tag.lyrics)
    set_tag("rating", str(tag.rating) if tag.rating > 0 else None)

    # Art via METADATA_BLOCK_PICTURE
    for k in list(t.keys()):
        if k.lower() == "metadata_block_picture":
            del t[k]

    if tag._staged_art_removed:
        pass  # already removed above
    elif tag._staged_art:
        pic = FLACPicture()
        pic.type = 3
        pic.mime = tag._staged_art_mime or "image/jpeg"
        pic.desc = ""
        pic.data = tag._staged_art
        t["metadata_block_picture"] = [
            base64.b64encode(pic.write()).decode("ascii")
        ]

    audio.save()


def _write_wavpack(tag: AudioTag):
    """Write tags to a WavPack file using APEv2 tags."""
    try:
        apev2 = APEv2(tag.path)
    except Exception:
        apev2 = APEv2()

    # Map AudioTag fields to APEv2 key names
    field_map = [
        ("Title",       tag.title),
        ("Artist",      tag.artist),
        ("Album",       tag.album),
        ("Album Artist",tag.album_artist),
        ("Composer",    tag.composer),
        ("Genre",       tag.genre),
        ("Year",        tag.year),
        ("Track",       tag.track),
        ("Disc",        tag.disc),
        ("Comment",     tag.comments),
        ("BPM",         tag.bpm),
        ("Lyrics",      tag.lyrics),
        ("Rating",      str(tag.rating) if tag.rating > 0 else None)
    ]
    for key, val in field_map:
        if val:
            apev2[key] = APETextValue(val, 0)  # kind=0 → UTF-8 text
        elif key in apev2:
            del apev2[key]

    # WavPack / APEv2 does not support embedded art in a standard way;
    # mutagen's APEv2 does support binary items but players vary widely.
    # We skip art for .wv to avoid corrupting files.

    apev2.save(tag.path)


_FORMAT_WRITERS = {
    ".mp3": _write_id3,
    ".wav": _write_id3,
    ".aif": _write_id3,
    ".aiff": _write_id3,
    ".flac": _write_flac,
    ".m4a": _write_mp4,
    ".aac": _write_mp4,
    ".mp4": _write_mp4,
    ".ogg": lambda tag: _write_vorbis(tag, OggVorbis),
    ".opus": lambda tag: _write_vorbis(tag, OggOpus),
    ".wv": _write_wavpack,
}


def save_tag(tag: AudioTag) -> None:
    """Write all tag fields (and staged art) to disk. Raises on failure."""
    ext = _ext(tag.path)
    writer = _FORMAT_WRITERS.get(ext)
    if writer is None:
        raise ValueError(f"Unsupported format: {ext}")
    writer(tag)
