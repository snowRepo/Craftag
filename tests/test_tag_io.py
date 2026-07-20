"""
test_tag_io.py — Round-trip read/write tests for Craftag's tag I/O layer.

Each format gets:
  - a basic field round-trip (write tags, re-read, assert values)
  - an art round-trip (write PNG bytes, re-read, assert bytes match; where supported)

Additional tests cover helper functions and edge cases.
"""
from __future__ import annotations

import os
import pytest

from craftag_py.core.tag_io import (
    AudioTag,
    read_tag,
    save_tag,
    read_art,
    _popm_to_stars,
    _stars_to_popm,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_and_read(path: str, **fields) -> AudioTag:
    """Apply *fields* to the tag at *path*, save, then re-read and return."""
    tag = read_tag(path)
    assert tag is not None, f"read_tag returned None for {path}"
    for k, v in fields.items():
        setattr(tag, k, v)
    tag.is_dirty = True
    save_tag(tag)
    return read_tag(path)


# ── Rating helpers ────────────────────────────────────────────────────────────

class TestRatingHelpers:
    def test_stars_to_popm_roundtrip(self):
        for stars in range(6):
            popm = _stars_to_popm(stars)
            assert _popm_to_stars(popm) == stars, f"round-trip failed for {stars} ★"

    def test_popm_to_stars_boundary(self):
        assert _popm_to_stars(0)   == 0
        assert _popm_to_stars(1)   == 1
        assert _popm_to_stars(64)  == 2
        assert _popm_to_stars(128) == 3
        assert _popm_to_stars(196) == 4
        assert _popm_to_stars(255) == 5

    def test_stars_to_popm_unknown_returns_zero(self):
        assert _stars_to_popm(99) == 0


# ── AudioTag dataclass ────────────────────────────────────────────────────────

class TestAudioTag:
    def test_defaults(self):
        tag = AudioTag(path="/tmp/x.mp3", filename="x.mp3")
        assert tag.is_dirty is False
        assert tag.rating == 0
        assert tag.has_art is False
        assert tag._staged_art is None

    def test_copy_is_independent(self):
        tag = AudioTag(path="/tmp/x.mp3", filename="x.mp3", title="Hello")
        copy = tag.copy()
        copy.title = "World"
        assert tag.title == "Hello"


# ── MP3 (ID3) ────────────────────────────────────────────────────────────────

class TestMp3RoundTrip:
    def test_basic_fields(self, tmp_mp3):
        result = _write_and_read(
            tmp_mp3,
            title="Test Track",
            artist="Test Artist",
            album="Test Album",
            year="2024",
            track="3",
            genre="Electronic",
            bpm="128",
        )
        assert result.title  == "Test Track"
        assert result.artist == "Test Artist"
        assert result.album  == "Test Album"
        assert result.year   == "2024"
        assert result.track  == "3"
        assert result.genre  == "Electronic"
        assert result.bpm    == "128"

    def test_comments(self, tmp_mp3):
        result = _write_and_read(tmp_mp3, comments="great song")
        assert result.comments == "great song"

    def test_lyrics(self, tmp_mp3):
        result = _write_and_read(tmp_mp3, lyrics="verse one\nverse two")
        assert result.lyrics is not None
        assert "verse one" in result.lyrics

    def test_rating(self, tmp_mp3):
        for stars in range(1, 6):
            result = _write_and_read(tmp_mp3, rating=stars)
            assert result.rating == stars, f"MP3 rating {stars} failed round-trip"

    def test_clear_field(self, tmp_mp3):
        _write_and_read(tmp_mp3, title="Will be cleared")
        result = _write_and_read(tmp_mp3, title=None)
        assert not result.title

    def test_art_roundtrip(self, tmp_mp3, small_png_bytes):
        tag = read_tag(tmp_mp3)
        tag._staged_art = small_png_bytes
        tag._staged_art_mime = "image/png"
        tag.is_dirty = True
        save_tag(tag)
        art = read_art(tmp_mp3)
        assert art is not None
        data, mime = art
        assert data == small_png_bytes
        assert "png" in mime

    def test_art_remove(self, tmp_mp3, small_png_bytes):
        # Set art then remove
        tag = read_tag(tmp_mp3)
        tag._staged_art = small_png_bytes
        tag._staged_art_mime = "image/png"
        tag.is_dirty = True
        save_tag(tag)

        tag2 = read_tag(tmp_mp3)
        tag2._staged_art_removed = True
        tag2.is_dirty = True
        save_tag(tag2)

        assert read_art(tmp_mp3) is None


# ── FLAC ─────────────────────────────────────────────────────────────────────

class TestFlacRoundTrip:
    def test_basic_fields(self, tmp_flac):
        result = _write_and_read(
            tmp_flac,
            title="FLAC Track",
            artist="FLAC Artist",
            album="FLAC Album",
            year="2023",
            genre="Classical",
            bpm="90",
        )
        assert result.title  == "FLAC Track"
        assert result.artist == "FLAC Artist"
        assert result.album  == "FLAC Album"
        assert result.year   == "2023"
        assert result.genre  == "Classical"
        assert result.bpm    == "90"

    def test_rating(self, tmp_flac):
        for stars in range(1, 6):
            result = _write_and_read(tmp_flac, rating=stars)
            assert result.rating == stars

    def test_lyrics(self, tmp_flac):
        result = _write_and_read(tmp_flac, lyrics="la la la")
        assert result.lyrics == "la la la"

    def test_art_roundtrip(self, tmp_flac, small_png_bytes):
        tag = read_tag(tmp_flac)
        tag._staged_art = small_png_bytes
        tag._staged_art_mime = "image/png"
        tag.is_dirty = True
        save_tag(tag)
        art = read_art(tmp_flac)
        assert art is not None
        data, mime = art
        assert data == small_png_bytes


# ── OGG Vorbis ───────────────────────────────────────────────────────────────

class TestOggRoundTrip:
    def test_basic_fields(self, tmp_ogg):
        result = _write_and_read(
            tmp_ogg,
            title="OGG Track",
            artist="OGG Artist",
            album="OGG Album",
            year="2022",
        )
        assert result.title  == "OGG Track"
        assert result.artist == "OGG Artist"
        assert result.album  == "OGG Album"
        assert result.year   == "2022"

    def test_rating(self, tmp_ogg):
        result = _write_and_read(tmp_ogg, rating=4)
        assert result.rating == 4

    def test_clear_field(self, tmp_ogg):
        _write_and_read(tmp_ogg, artist="Temp")
        result = _write_and_read(tmp_ogg, artist=None)
        assert not result.artist


# ── Opus ─────────────────────────────────────────────────────────────────────

class TestOpusRoundTrip:
    def test_basic_fields(self, tmp_opus):
        result = _write_and_read(
            tmp_opus,
            title="Opus Track",
            artist="Opus Artist",
        )
        assert result.title  == "Opus Track"
        assert result.artist == "Opus Artist"

    def test_lyrics(self, tmp_opus):
        result = _write_and_read(tmp_opus, lyrics="do re mi")
        assert result.lyrics == "do re mi"


# ── M4A ──────────────────────────────────────────────────────────────────────

class TestM4aRoundTrip:
    def test_basic_fields(self, tmp_m4a):
        result = _write_and_read(
            tmp_m4a,
            title="M4A Track",
            artist="M4A Artist",
            album="M4A Album",
            year="2021",
            genre="Pop",
        )
        assert result.title  == "M4A Track"
        assert result.artist == "M4A Artist"
        assert result.album  == "M4A Album"
        assert result.year   == "2021"
        assert result.genre  == "Pop"

    def test_track_number(self, tmp_m4a):
        result = _write_and_read(tmp_m4a, track="5")
        assert result.track == "5"

    def test_bpm(self, tmp_m4a):
        result = _write_and_read(tmp_m4a, bpm="120")
        assert result.bpm == "120"

    def test_art_roundtrip(self, tmp_m4a, small_png_bytes):
        tag = read_tag(tmp_m4a)
        tag._staged_art = small_png_bytes
        tag._staged_art_mime = "image/png"
        tag.is_dirty = True
        save_tag(tag)
        art = read_art(tmp_m4a)
        assert art is not None


# ── read_tag edge cases ───────────────────────────────────────────────────────

class TestReadTagEdgeCases:
    def test_unsupported_extension_returns_none(self, tmp_path):
        f = tmp_path / "audio.xyz"
        f.write_bytes(b"dummy")
        assert read_tag(str(f)) is None

    def test_nonexistent_file_returns_none(self):
        assert read_tag("/nonexistent/path/audio.mp3") is None

    def test_read_tag_mp3_no_tags(self, tmp_mp3):
        """read_tag should succeed even when the file has no existing ID3 header."""
        tag = read_tag(tmp_mp3)
        assert tag is not None
        assert tag.path == tmp_mp3
        assert tag.rating == 0
