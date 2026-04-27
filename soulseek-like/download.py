#!/usr/bin/env python3
"""
Nova-Tunes Downloader — slskd API wrapper (v4)

Search and download music via Soulseek network through slskd daemon.
Falls back to yt-dlp if slskd is unreachable.

Usage:
    python3 download.py "artist - song title"     Download best match
    python3 download.py "artist - song title" --list   Show top results only
"""

import argparse
import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

SLSKD_BASE = "http://localhost:5030"
WEB_USER = "slskd"
WEB_PASS = "slskd"


@dataclass
class Track:
    filename: str
    size: int       # bytes
    username: str
    bitrate: int    # kbps (from bitRate field)
    extension: str
    length: int     # seconds
    sample_rate: int
    bit_depth: int


def api_session() -> str:
    """Get slskd Bearer token."""
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{SLSKD_BASE}/api/v0/session",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"username": WEB_USER, "password": WEB_PASS})],
        capture_output=True, text=True, timeout=10
    )
    return json.loads(r.stdout)["token"]


def api_get(path: str, token: str) -> dict | list:
    r = subprocess.run(
        ["curl", "-s", f"{SLSKD_BASE}/api/v0/{path}",
         "-H", f"Authorization: Bearer {token}"],
        capture_output=True, text=True, timeout=10
    )
    return json.loads(r.stdout)


def api_post(path: str, token: str, data: dict) -> dict | list:
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{SLSKD_BASE}/api/v0/{path}",
         "-H", "Content-Type: application/json",
         "-H", f"Authorization: Bearer {token}",
         "-d", json.dumps(data)],
        capture_output=True, text=True, timeout=10
    )
    return json.loads(r.stdout)


def search_soulseek(query: str, limit: int = 100, timeout: int = 40) -> list[Track]:
    """
    Search Soulseek for tracks matching query.
    Polls until results arrive or timeout.
    Returns list of Track objects sorted by quality (best first).
    """
    token = api_session()
    search_id = str(uuid.uuid4())

    # Start search
    api_post("searches", token, {"id": search_id, "searchText": query})

    deadline = time.time() + timeout
    tracks = []
    poll_interval = 2  # seconds between polls

    while time.time() < deadline:
        time.sleep(poll_interval)
        state = api_get(f"searches/{search_id}", token)

        search_state = state.get("state", "")
        rc = state.get("responseCount", 0)

        # Wait for search to finish (Completed, Failed, etc.)
        if "Completed" in search_state or "Failed" in search_state:
            # Files may not be immediately available — retry until we get them
            for retry in range(5):
                time.sleep(2)
                responses = api_get(f"searches/{search_id}/responses", token)
                total_files = sum(len(r.get("files", [])) for r in responses)
                if total_files > 0 or retry >= 4:
                    break
            for resp in responses:
                username = resp.get("username", "unknown")
                for f in resp.get("files", []):
                    tracks.append(Track(
                        filename=f.get("filename", ""),
                        size=f.get("size", 0),
                        username=username,
                        bitrate=f.get("averageBitRate", 0) or f.get("bitRate", 0),
                        extension=f.get("extension", ""),
                        length=f.get("length", 0),
                        sample_rate=f.get("sampleRate", 0),
                        bit_depth=f.get("bitDepth", 0)
                    ))
            break

    # Sort: FLAC > MP3 320 > MP3 192 > ... then by size
    def quality(t: Track) -> tuple:
        ext_score = {"flac": 4, "alac": 3, "wav": 2, "mp3": 1}.get(t.extension.lower(), 0)
        return (ext_score, t.bitrate, t.size)
    tracks.sort(key=quality, reverse=True)
    return tracks[:limit]


def pick_best_album(tracks: list[Track], query: str) -> list[Track]:
    """
    From a list of tracks, pick the best album matching the query.
    Groups by album (derived from filename path) and returns the album
    with the most tracks and best quality.
    """
    if not tracks:
        return []

    # Group by directory (album)
    albums: dict[str, list[Track]] = {}
    for t in tracks:
        # Filenames are like: Music\Artist\Album\Track.ext or Artist\Album\Track.ext
        parts = t.filename.replace("/", "\\").split("\\")
        if len(parts) >= 2:
            album_key = "\\".join(parts[:-1])  # everything except track name
        else:
            album_key = t.filename
        if album_key not in albums:
            albums[album_key] = []
        albums[album_key].append(t)

    # Score each album
    def album_score(item: tuple) -> tuple:
        album_key, album_tracks = item
        # Count tracks, prefer FLAC, prefer complete albums
        ext = album_tracks[0].extension.lower() if album_tracks else ""
        ext_score = {"flac": 4, "alac": 3, "wav": 2, "mp3": 1}.get(ext, 0)
        avg_bitrate = sum(t.bitrate for t in album_tracks) / len(album_tracks) if album_tracks else 0
        return (len(album_tracks), ext_score, avg_bitrate)

    best_album_key = max(albums.items(), key=album_score)[0]
    return albums[best_album_key]


def enqueue_download(tracks: list[Track], token: str) -> list[str]:
    """
    Enqueue a list of tracks for download.
    Returns list of transfer IDs.
    """
    transfer_ids = []
    # Group by username (one POST per user)
    by_user: dict[str, list[Track]] = {}
    for t in tracks:
        by_user.setdefault(t.username, []).append(t)

    for username, user_tracks in by_user.items():
        files = [{"filename": t.filename, "size": t.size} for t in user_tracks]
        r = subprocess.run(
            ["curl", "-s", "-X", "POST",
             f"{SLSKD_BASE}/api/v0/transfers/downloads/{username}",
             "-H", "Content-Type: application/json",
             "-H", f"Authorization: Bearer {token}",
             "-d", json.dumps(files)],
            capture_output=True, text=True, timeout=15
        )
        try:
            result = json.loads(r.stdout)
            if isinstance(result, list):
                for t in result:
                    tid = t.get("id", "")
                    if tid:
                        transfer_ids.append(tid)
        except:
            pass
    return transfer_ids


def get_active_transfers(token: str) -> list[dict]:
    r = subprocess.run(
        ["curl", "-s", f"{SLSKD_BASE}/api/v0/transfers/downloads",
         "-H", f"Authorization: Bearer {token}"],
        capture_output=True, text=True, timeout=10
    )
    return json.loads(r.stdout) if r.stdout else []


def download_ytdlp(query: str) -> bool:
    """Fallback to yt-dlp for YouTube/SoundCloud."""
    cmd = ["/home/niko/bin/yt-dlp", "--no-playlist", "-x", "--audio-format", "mp3",
           "-o", "/tmp/nova-tunes.%(ext)s", f"ytsearch1:{query}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0


def format_size(size: int) -> str:
    mb = size / 1024 / 1024
    if mb >= 1024:
        return f"{mb/1024:.1f} GB"
    return f"{mb:.1f} MB"


def format_length(s: int) -> str:
    m = s // 60
    sec = s % 60
    return f"{m}:{sec:02d}"


def main():
    parser = argparse.ArgumentParser(description="Nova-Tunes downloader")
    parser.add_argument("query", help="Search query (artist - title)")
    parser.add_argument("--list", action="store_true", help="Show results only, don't download")
    parser.add_argument("--limit", type=int, default=100, help="Max results (default: 100)")
    parser.add_argument("--timeout", type=int, default=40, help="Search timeout seconds (default: 40)")
    args = parser.parse_args()

    print(f"[{time.strftime('%H:%M:%S')}] Recherche Soulseek : {args.query!r}")

    # Step 1: Search
    try:
        all_tracks = search_soulseek(args.query, limit=args.limit, timeout=args.timeout)
    except Exception as e:
        print(f"  Erreur Soulseek: {e}")
        print("  Fallback: yt-dlp...")
        ok = download_ytdlp(args.query)
        sys.exit(0 if ok else 1)

    if not all_tracks:
        print("  Aucun résultat.")
        print("  Fallback: yt-dlp...")
        ok = download_ytdlp(args.query)
        sys.exit(0 if ok else 1)

    print(f"  {len(all_tracks)} fichiers trouvés")

    # Step 2: Pick best album
    album_tracks = pick_best_album(all_tracks, args.query)
    if not album_tracks:
        album_tracks = all_tracks[:10]

    # Unique album path for display
    album_name = album_tracks[0].filename.replace("/", "\\").split("\\")[-2] if album_tracks else "?"
    print(f"  Album sélectionné: {album_name} ({len(album_tracks)} titres)")

    if args.list:
        print(f"\n  Top résultats ({min(10, len(all_tracks))}):")
        shown = set()
        for t in all_tracks:
            key = (t.filename, t.username)
            if key in shown:
                continue
            shown.add(key)
            ext = t.extension.upper() or "?"
            br = f"{t.bitrate}kbps" if t.bitrate else "?"
            size = format_size(t.size)
            name = Path(t.filename.replace("\\", "/")).name
            print(f"  [{ext}] {br:>8s}  {size:>8s}  {name}  ({t.username})")
            if len(shown) >= 10:
                break
        return

    # Step 3: Enqueue all album tracks
    print(f"\n  Enqueue de {len(album_tracks)} titres...")
    try:
        token = api_session()
        transfer_ids = enqueue_download(album_tracks, token)
        print(f"  {len(transfer_ids)} transferts lancés")
    except Exception as e:
        print(f"  Erreur enqueue: {e}")
        sys.exit(1)

    # Step 4: Poll until done
    print(f"  Suivi des transferts...")
    last_states = {}
    completed = 0
    failed = 0

    while True:
        time.sleep(8)
        try:
            transfers = get_active_transfers(token)
        except:
            break

        active = 0
        for t in (transfers if isinstance(transfers, list) else []):
            tid = t.get("id", "")
            state = t.get("state", "?")
            filename = Path(t.get("file", {}).get("filename", "?") or "?").name
            progress = t.get("progress", 0)

            if "Completed" in state or "Succeeded" in state:
                completed += 1
                if state != last_states.get(tid):
                    print(f"  [OK]   {filename}")
                    last_states[tid] = state
            elif "Failed" in state or "Error" in state:
                failed += 1
                if state != last_states.get(tid):
                    print(f"  [FAIL] {filename}: {state}")
                    last_states[tid] = state
            else:
                active += 1
                if state != last_states.get(tid):
                    print(f"  {state:20s}  {filename} ({progress}%)")
                    last_states[tid] = state

        total = len(album_tracks)
        print(f"  --- {completed}/{total} complétés, {failed} échoués, {active} actifs ---")
        if completed + failed >= total:
            break


if __name__ == "__main__":
    main()
