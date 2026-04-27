#!/usr/bin/env python3
"""
Nova-Tunes Downloader — slskd API wrapper (v2)
Search and download music via Soulseek network through slskd daemon.
Usage: python3 download.py "artist - song title"
"""

import sys
import json
import argparse
import time
import uuid
import requests
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────
SLSKD_BASE   = "http://localhost:5030"
SLSKD_API    = f"{SLSKD_BASE}/api/v0"
MUSIC_DIR    = Path(__file__).parent.parent / "music"
DATA_DIR     = Path(__file__).parent.parent / "data"
LOG_FILE     = DATA_DIR / "download.log"
WEB_USER     = "slskd"
WEB_PASS     = "slskd"
API_TIMEOUT  = 30
RATE_LIMIT  = 1.0   # seconds between requests

# ── Helpers ───────────────────────────────────────────────────────────────
def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(LOG_FILE.read_text() + line + "\n" if LOG_FILE.exists() else line + "\n")

def get_token():
    r = requests.post(
        f"{SLSKD_API}/session",
        json={"username": WEB_USER, "password": WEB_PASS},
        timeout=API_TIMEOUT
    )
    r.raise_for_status()
    return r.json()["token"]

def api_get(path, token, params=None):
    r = requests.get(
        f"{SLSKD_API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=API_TIMEOUT
    )
    r.raise_for_status()
    return r.json()

def api_post(path, token, json=None):
    r = requests.post(
        f"{SLSKD_API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        json=json,
        timeout=API_TIMEOUT
    )
    r.raise_for_status()
    return r.json()

def wait():
    time.sleep(RATE_LIMIT)

# ── Core actions ──────────────────────────────────────────────────────────
def do_search(token, query, limit=8, poll_interval=3, max_polls=8):
    """Launch search and poll until results arrive."""
    search_id = str(uuid.uuid4())
    log(f"Recherche Soulseek : '{query}'")

    # Launch search
    api_post("/searches", token, {"id": search_id, "searchText": query})

    # Poll for results
    for _ in range(max_polls):
        time.sleep(poll_interval)
        result = api_get(f"/searches/{search_id}", token, params={"includeResponses": "true"})
        state = result.get("state", "")
        response_count = result.get("responseCount", 0)

        if state == "InProgress" and response_count > 0:
            # Got some responses, keep polling for more
            if response_count >= limit:
                break
        elif state.startswith("Completed"):
            break

    log(f"  -> {response_count} reponses, {result.get('fileCount', 0)} fichiers")

    # Collect all files from all responses
    files = []
    for resp in result.get("responses", []):
        username = resp.get("username", "")
        for f in resp.get("files", []):
            f["_username"] = username
            files.append(f)

    return files

def pick_best(files, n=5):
    """Pick best quality files: prefer mp3/flac, larger size."""
    def score(f):
        name = f.get("filename", "")
        size = f.get("size", 0)
        ext  = name.lower().split(".")[-1] if "." in name else ""
        q    = 100 if ext in {"mp3", "flac"} else (50 if ext in {"m4a", "aac", "wav"} else 10)
        # Penalize guitar pro tabs
        if "guitar pro" in name.lower() or ext in {"gp3", "gp4", "gp5", "gpx"}:
            q = 1
        return q * 1_000_000_000 + size

    files.sort(key=score, reverse=True)
    return files[:n]

def enqueue_download(token, file_entry):
    """Enqueue a single file for download."""
    f = file_entry
    username = f.get("_username", "")
    filename = f.get("filename", "")
    size     = f.get("size", 0)
    length   = f.get("length", 0)
    bitrate  = f.get("bitrate", 0)

    payload = [{
        "username":  username,
        "filename": filename,
        "size":     size,
        "length":   length,
        "bitrate":  bitrate,
    }]

    log(f"Enqueue: {filename.split(chr(92))[-1]} ({size // (1024*1024)} MB) depuis @{username}")
    result = api_post(f"/transfers/downloads/{username}", token, payload)

    enqueued = result.get("enqueued", [])
    if enqueued:
        t = enqueued[0]
        log(f"  -> Queue position: {t.get('state')} | {t.get('id')}")
    return result

def get_downloads(token):
    """Return list of active/recent downloads."""
    return api_get("/transfers/downloads", token)

# ── CLI ──────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Nova-Tunes downloader via slskd Soulseek API")
    p.add_argument("query", nargs="?", help="Search query (artist - title)")
    p.add_argument("--limit", "-n", type=int, default=8, help="Max results to search (default: 8)")
    p.add_argument("--top", "-t", action="store_true", help="Download top result only (default)")
    p.add_argument("--all", "-a", action="store_true", help="Download all results (up to --limit)")
    p.add_argument("--list", "-l", action="store_true", help="Search and list results only (no download)")
    p.add_argument("--status", "-s", action="store_true", help="Show download queue")
    args = p.parse_args()

    # Get auth token
    try:
        token = get_token()
    except Exception as e:
        log(f"ERREUR: Impossible de se connecter a slskd: {e}")
        sys.exit(1)

    if args.status:
        downloads = get_downloads(token)
        print(f"\n  Download queue ({len(downloads) if isinstance(downloads, list) else '?'} items):\n")
        if isinstance(downloads, list):
            for t in downloads:
                fname = t.get("filename", "?")
                # Get last part of path
                if chr(92) in fname:
                    fname = fname.split(chr(92))[-1]
                state = t.get("state", "?")
                pct   = t.get("percentComplete", 0)
                speed = t.get("averageSpeed", 0)
                print(f"  [{pct:3d}%] {fname}")
                print(f"         {state} | {speed//1024} KB/s")
        else:
            print(json.dumps(downloads, indent=2)[:500])
        return

    if not args.query:
        p.print_help()
        return

    files = do_search(token, args.query, limit=args.limit)
    if not files:
        log("Aucun resultat.")
        return

    best = pick_best(files, n=args.limit)

    print(f"\n  Resultats pour '{args.query}' (top {len(best)}):\n")
    for i, f in enumerate(best, 1):
        fname = f.get("filename", "?")
        if chr(92) in fname:
            fname = fname.split(chr(92))[-1]
        size = f.get("size", 0) // (1024*1024)
        user = f.get("_username", "?")
        bitrate = f.get("bitrate", 0)
        print(f"  [{i}] {fname}  ({size} MB) @{user} {bitrate}kbps")
    print()

    if args.list:
        return

    to_download = best if args.all else [best[0]]

    for f in to_download:
        enqueue_download(token, f)
        wait()

    log(f"-> {len(to_download)} fichier(s) ajoutes a la queue.")
    print(f"\n  Telechargement en cours... http://localhost:5030\n")

if __name__ == "__main__":
    main()
