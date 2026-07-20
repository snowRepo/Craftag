"""
musicbrainz.py — iTunes Search API lookup helpers for Craftag Auto-Fill.

Uses Apple's iTunes Search API (no API key required) for highly accurate,
label-sourced metadata. The public interface is identical to the old
MusicBrainz implementation so editor_panel.py needs no changes.

Intentionally uses only stdlib (urllib, json, ssl) — no new dependencies.
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request
from typing import Optional

_API_BASE = "https://itunes.apple.com/search"
_TIMEOUT  = 10          # socket timeout in seconds
_UA       = "Craftag/2.0.0 (github.com/snowRepo/Craftag)"


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def lookup_recording(title: str, artist: str = "") -> Optional[dict]:
    """Look up track metadata via the iTunes Search API.

    Searches by *title* + optional *artist*.  Returns a dict with any subset
    of the keys:  artist, album, album_artist, year, track, genre

    Returns None if no matching track is found.
    Raises RuntimeError on unrecoverable network errors (after retries).
    """
    # Build the search query
    query_parts = [title]
    if artist:
        query_parts.append(artist)

    params = urllib.parse.urlencode({
        "term":   " ".join(query_parts),
        "media":  "music",
        "entity": "song",
        "limit":  5,
    })
    url = f"{_API_BASE}?{params}"

    raw = _fetch_with_retry(url)

    try:
        response = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from iTunes: {exc}") from exc

    results = response.get("results", [])
    if not results:
        return None

    hit = results[0]
    data: dict = {}

    # ── Artist ────────────────────────────────────────────────────────────
    artist_name = (hit.get("artistName") or "").strip()
    if artist_name:
        data["artist"] = artist_name

    # ── Album ─────────────────────────────────────────────────────────────
    album = (hit.get("collectionName") or "").strip()
    if album:
        data["album"] = album

    # ── Album artist ──────────────────────────────────────────────────────
    # collectionArtistName is set for compilations; fall back to track artist
    album_artist = (hit.get("collectionArtistName") or "").strip()
    if album_artist and album_artist.lower() != "various artists":
        data["album_artist"] = album_artist
    elif artist_name:
        data["album_artist"] = artist_name

    # ── Year ──────────────────────────────────────────────────────────────
    release_date = (hit.get("releaseDate") or "").strip()
    if release_date:
        data["year"] = release_date[:4]          # "2009-09-15T…" → "2009"

    # ── Track number ──────────────────────────────────────────────────────
    track_num = hit.get("trackNumber")
    if track_num:
        data["track"] = str(track_num)

    # ── Genre ─────────────────────────────────────────────────────────────
    genre = (hit.get("primaryGenreName") or "").strip()
    if genre and genre.lower() != "music":       # "Music" is too generic
        data["genre"] = genre

    return data if data else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_with_retry(url: str, attempts: int = 3, delay: float = 1.5) -> bytes:
    """GET *url*, retrying up to *attempts* times on transient SSL/network errors."""
    ctx = ssl.create_default_context()
    last_exc: Exception | None = None

    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp:
                return resp.read()
        except (ssl.SSLError, OSError) as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(delay)
        except Exception:
            raise   # non-network errors (e.g. HTTP 4xx) bubble up immediately

    raise RuntimeError(
        f"Network error after {attempts} attempts: {last_exc}. "
        "Check your internet connection and try again."
    )
