#!/usr/bin/env python3
"""
Nova-Tunes Downloader — slskd API wrapper (v3)

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
    size: int  # bytes
    username: str
    bitrate: int
    extension: str
    length: int  # seconds


def api_session() -> str:
    """Get slskd Bearer token."""
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{SLSKD_BASE}/api/v0/session",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"username": WEB_USER, "password": WEB_PASS})],
        capture_output=True, text=True
    )
    return json.loads(r.stdout)["token"]


def api_get(path: str, token: str) -> dict | list:
    r = subprocess.run(
        ["curl", "-s", f"{SLSKD_BASE}/api/v0/{path}",
         "-H", f"Authorization: Bearer {token}"],
        capture_output=True, text=True
    )
    return json.loads(r.stdout)


def api_post(path: str, token: str, data: dict) -> dict | list:
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{SLSKD_BASE}/api/v0/{path}",
         "-H", "Content-Type: application/json",
         "-H", f"Authorization: Bearer {token}",
         "-d", json.dumps(data)],
        capture_output=True, text=True
    )
    return json.loads(r.stdout)


def search_soulseek(query: str, limit: int = 50, timeout: int = 30) -> list[Track]:
    """
    Search Soulseek for tracks matching query.
    Polls until results arrive or timeout.
    Returns list of Track objects sorted by bitrate (best first).
    """
    token = api_session()
    search_id = str(uuid.uuid4())

    api_post("searches", token, {"id": search_id, "searchText": query})

    # Poll until we get responses
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        state = api_get(f"searches/{search_id}", token)
        if state.get("responseCount", 0) > 0:
            break

    # Fetch all responses
    responses = api_get(f"searches/{search_id}/responses", token)

    tracks = []
    for resp in responses:
        username = resp.get("username", "unknown")
        for f in resp.get("files", []):
            tracks.append(Track(
                filename=f.get("filename", ""),
                size=f.get("size", 0),
                username=username,
                bitrate=f.get("bitRate", 0),
                extension=f.get("extension", ""),
                length=f.get("length", 0)
            ))

    # Sort: highest bitrate first, then by size descending
    tracks.sort(key=lambda t: (t.bitrate * -1, t.size * -1))
    return tracks[:limit]


def pick_best_track(tracks: list[Track]) -> Track:
    """Pick the best quality track (highest bitrate, then largest size)."""
    return tracks[0]


def enqueue_download(track: Track, token: str) -> str:
    """
    Enqueue a track for download.
    Returns transfer ID.
    """
    # The file needs to be sent as: { "filename": "...", "size": N }
    file_desc = {"filename": track.filename, "size": track.size}

    # POST /transfers/downloads/{username} with array of files
    r = subprocess.run(
        ["curl", "-s", "-X", "POST",
         f"{SLSKD_BASE}/api/v0/transfers/downloads/{track.username}",
         "-H", "Content-Type: application/json",
         "-H", f"Authorization: Bearer {token}",
         "-d", json.dumps([file_desc])],
        capture_output=True, text=True
    )
    result = json.loads(r.stdout)
    # Returns list of enqueued transfers
    if isinstance(result, list) and result:
        return result[0].get("id", "")
    return ""


def get_transfer_status(token: str) -> list[dict]:
    r = subprocess.run(
        ["curl", "-s", f"{SLSKD_BASE}/api/v0/transfers/downloads",
         "-H", f"Authorization: Bearer {token}"],
        capture_output=True, text=True
    )
    return json.loads(r.stdout)


def download_ytdlp(query: str) -> bool:
    """Fallback to yt-dlp for YouTube/SoundCloud."""
    cmd = ["/home/niko/bin/yt-dlp", "--no-playlist", "-x", "--audio-format", "mp3",
           "-o", "/tmp/nova-tunes.%(ext)s", f"ytsearch1:{query}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  [yt-dlp] Downloaded via YouTube")
        return True
    return False


def format_size(size: int) -> str:
    mb = size / 1024 / 1024
    if mb >= 1024:
        return f"{mb/1024:.1f} GB"
    return f"{mb:.1f} MB"


def format_bitrate(br: int) -> str:
    return f"{br} kbps" if br else "?"


def main():
    parser = argparse.ArgumentParser(description="Nova-Tunes downloader")
    parser.add_argument("query", help="Search query (artist - title)")
    parser.add_argument("--list", action="store_true", help="Show results only, don't download")
    parser.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    parser.add_argument("--timeout", type=int, default=30, help="Search timeout seconds (default: 30)")
    args = parser.parse_args()

    print(f"[{time.strftime('%H:%M:%S')}] Recherche Soulseek : {args.query!r}")

    try:
        tracks = search_soulseek(args.query, limit=args.limit, timeout=args.timeout)
    except Exception as e:
        print(f"  Erreur Soulseek: {e}")
        print("  Fallback: yt-dlp...")
        ok = download_ytdlp(args.query)
        sys.exit(0 if ok else 1)

    if not tracks:
        print("  Aucun résultat.")
        print("  Fallback: yt-dlp...")
        ok = download_ytdlp(args.query)
        sys.exit(0 if ok else 1)

    if args.list:
        print(f"  {len(tracks)} fichiers trouvés (top {min(10, len(tracks))}):")
        for i, t in enumerate(tracks[:10]):
            ext = t.extension.upper()
            print(f"  {i+1:2d}. [{ext}] {format_bitrate(t.bitrate):>8s}  {format_size(t.size):>8s}  {t.filename}  ({t.username})")
        return

    track = pick_best_track(tracks)
    print(f"  -> Meilleure correspondance: {track.filename}")
    print(f"     {format_bitrate(track.bitrate)}  {format_size(track.size)}  de {track.username}")

    # Strip path prefix for display (Soulseek paths are like: music/Artist/Album/...)
    display_name = Path(track.filename).name
    print(f"  Enqueue pour téléchargement...")

    try:
        token = api_session()
        transfer_id = enqueue_download(track, token)
        if transfer_id:
            print(f"  Transfert lancé (ID: {transfer_id[:8]}...)")
        else:
            print(f"  Transfert en cours...")
    except Exception as e:
        print(f"  Erreur download: {e}")
        sys.exit(1)

    # Poll until done
    print(f"  Suivi du transfert...")
    last_state = ""
    while True:
        time.sleep(5)
        try:
            transfers = get_transfer_status(token)
        except:
            break
        # Find our transfer
        ours = None
        for t in (transfers if isinstance(transfers, list) else []):
            if track.filename in str(t):
                ours = t
                break
        if not ours:
            # Download completed (removed from active list)
            print(f"  [OK] Téléchargement terminé!")
            break
        state = ours.get("state", "?")
        if state != last_state:
            print(f"  -> {state}")
            last_state = state
        if "Completed" in state or "Succeeded" in state:
            print(f"  [OK] {state}")
            break
        if "Failed" in state or "Error" in state:
            print(f"  [ERREUR] {state}")
            break


if __name__ == "__main__":
    main()
