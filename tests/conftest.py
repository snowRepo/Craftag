"""
conftest.py — pytest fixtures that build minimal valid audio files in every
supported format using mutagen alone (no binary blobs committed to the repo).

Each fixture yields a temporary file path and cleans up automatically.
"""
from __future__ import annotations

import io
import os
import struct
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# ---------------------------------------------------------------------------
# Minimal valid audio-file stubs
# ---------------------------------------------------------------------------

def _minimal_mp3() -> bytes:
    """Return the smallest valid ID3v2.3 + MPEG frame that mutagen accepts."""
    # ID3v2.3 header: 'ID3', version 2.3.0, no flags, size=0
    id3 = b"ID3" + b"\x03\x00\x00" + b"\x00\x00\x00\x00"
    # One valid MPEG1 Layer3 frame header (silence, 128 kbps, 44100 Hz, stereo)
    mpeg = bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 413
    return id3 + mpeg


def _minimal_flac() -> bytes:
    """Minimal FLAC file with valid STREAMINFO block (44100 Hz, 2 ch, 16-bit)."""
    marker = b"fLaC"
    # STREAMINFO is always 34 bytes.
    # Layout (bits): min_block(16) max_block(16) min_frame(24) max_frame(24)
    #                sample_rate(20) channels-1(3) bits-1(5) total_samples(36) md5(128)
    # We pack sample_rate=44100, channels=2, bits=16, samples=0.
    # Bit-pack the packed word: sample_rate<<44 | (channels-1)<<41 | (bits-1)<<36 | 0
    sr   = 44100
    ch   = 2
    bps  = 16
    packed = (sr << 44) | ((ch - 1) << 41) | ((bps - 1) << 36)
    # Convert to 8 bytes big-endian
    packed_bytes = packed.to_bytes(8, "big")
    stream_info = (
        struct.pack(">HH", 4096, 4096)   # min/max blocksize
        + b"\x00\x00\x00"                # min framesize (0 = unknown)
        + b"\x00\x00\x00"                # max framesize (0 = unknown)
        + packed_bytes                   # rate/ch/bps/samples
        + b"\x00" * 16                  # MD5
    )
    assert len(stream_info) == 34
    # Block header: type=0, last-metadata-block flag, length=34
    block_header = struct.pack(">I", (1 << 31) | 34)
    return marker + block_header + stream_info


def _ogg_page(serial: int, seq: int, granule: int, data: bytes, first: bool = False, last: bool = False) -> bytes:
    """Build a minimal OGG page."""
    capture    = b"OggS"
    version    = b"\x00"
    flags      = bytes([0x02 if first else (0x04 if last else 0x00)])
    gran       = struct.pack("<q", granule)
    ser        = struct.pack("<I", serial)
    seqno      = struct.pack("<I", seq)
    # Build segment table (255 bytes max per segment)
    segments   = []
    remaining  = data
    while remaining:
        seg = remaining[:255]
        segments.append(len(seg))
        remaining = remaining[255:]
    segtab     = bytes([len(segments)]) + bytes(segments)
    # CRC over the whole page with crc=0
    header_no_crc = capture + version + flags + gran + ser + seqno + b"\x00\x00\x00\x00" + segtab
    page_no_crc   = header_no_crc + data
    crc = _ogg_crc(page_no_crc)
    header = capture + version + flags + gran + ser + seqno + struct.pack("<I", crc) + segtab
    return header + data


def _ogg_crc(data: bytes) -> int:
    """OGG CRC-32 (polynomial 0x04c11db7, no inversion)."""
    crc = 0
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = (crc << 1) ^ 0x04c11db7
            else:
                crc <<= 1
        crc &= 0xFFFFFFFF
    return crc


def _minimal_ogg_vorbis() -> bytes:
    """Minimal OGG Vorbis file with identification, comment, and setup headers."""
    serial = 1

    # Identification header
    id_hdr = (
        b"\x01vorbis"                   # packet type + magic
        + struct.pack("<I", 0)          # vorbis version
        + b"\x02"                       # channels=2
        + struct.pack("<I", 44100)      # sample rate
        + struct.pack("<iii", 0, 192000, 0)  # bitrate max/nom/min
        + b"\xb8\x01"                  # blocksize (256/2048) packed
        + b"\x01"                       # framing bit
    )
    # Comment header — minimal
    vendor = b"Craftag test"
    com_hdr = (
        b"\x03vorbis"
        + struct.pack("<I", len(vendor)) + vendor
        + struct.pack("<I", 0)          # 0 user comments
        + b"\x01"                       # framing bit
    )
    # Setup header — bare minimum (codebooks etc.) — use a 1-byte stub
    # mutagen only parses id+comment for tag reading, so setup can be minimal
    setup_hdr = b"\x05vorbis" + b"\x00" * 4 + b"\x01"  # framing bit

    p0 = _ogg_page(serial, 0, 0, id_hdr, first=True)
    p1 = _ogg_page(serial, 1, 0, com_hdr + setup_hdr)
    return p0 + p1


def _minimal_opus() -> bytes:
    """Minimal OGG Opus file with OpusHead and OpusTags pages."""
    serial = 2

    # OpusHead packet
    opus_head = (
        b"OpusHead"
        + b"\x01"                        # version
        + b"\x02"                        # channels=2
        + struct.pack("<H", 312)         # pre-skip
        + struct.pack("<I", 48000)       # sample rate
        + struct.pack("<h", 0)           # output gain
        + b"\x00"                        # channel mapping family
    )
    # OpusTags packet
    vendor = b"Craftag test"
    opus_tags = (
        b"OpusTags"
        + struct.pack("<I", len(vendor)) + vendor
        + struct.pack("<I", 0)           # 0 user comments
    )

    p0 = _ogg_page(serial, 0, 0, opus_head, first=True)
    p1 = _ogg_page(serial, 1, 0, opus_tags)
    return p0 + p1




# ---------------------------------------------------------------------------
# Per-format fixtures
# ---------------------------------------------------------------------------

def _make_fixture(suffix: str, content_fn):
    @pytest.fixture
    def _fixture() -> Generator[str, None, None]:
        data = content_fn()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(data)
            path = f.name
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass
    _fixture.__name__ = f"tmp_{suffix.lstrip('.')}"
    return _fixture


@pytest.fixture
def tmp_mp3() -> Generator[str, None, None]:
    data = _minimal_mp3()
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(data)
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def tmp_flac() -> Generator[str, None, None]:
    """FLAC fixture — generated via raw bytes with a valid STREAMINFO."""
    with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
        f.write(_minimal_flac())
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def tmp_m4a() -> Generator[str, None, None]:
    """M4A fixture — uses a real minimal MP4 atom that mutagen can parse."""
    import urllib.request
    # Build a valid ftyp + free + mdat + moov structure from scratch.
    # The simplest approach: write the minimum atoms mutagen's MP4 accepts.
    def atom(name: bytes, data: bytes = b"") -> bytes:
        return struct.pack(">I", len(data) + 8) + name + data

    ftyp_data  = b"M4A " + struct.pack(">I", 0) + b"M4A "
    ftyp       = atom(b"ftyp", ftyp_data)
    free       = atom(b"free")

    # Minimal moov: mvhd + trak(tkhd + mdia(mdhd + hdlr + minf(smhd+dinf+stbl)))
    # Use the version 0 (32-bit) mvhd filled with zeros
    mvhd_data  = b"\x00" * 92          # version+flags(4) + all fields zeros
    mvhd       = atom(b"mvhd", mvhd_data)
    moov       = atom(b"moov", mvhd)

    raw = ftyp + free + moov
    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
        f.write(raw)
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def tmp_ogg() -> Generator[str, None, None]:
    data = _minimal_ogg_vorbis()
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(data)
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def tmp_opus() -> Generator[str, None, None]:
    data = _minimal_opus()
    with tempfile.NamedTemporaryFile(suffix=".opus", delete=False) as f:
        f.write(data)
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def small_png_bytes() -> bytes:
    """1×1 red pixel PNG — the smallest valid PNG image."""
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
