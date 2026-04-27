#!/usr/bin/env python3
"""
Nova-Tunes Downloader — slskd API wrapper
Search and download music via Soulseek network through slskd daemon.
Usage: python3 download.py "artist - song title"
"""

import sys
import json
import argparse
import time
import requests
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────
SLSKD_BASE   = "http://localhost:5030"
MUSIC_DIR    = Path(__file__).parent.parent / "music"
DATA_DIR     = Path(__file__).parent.parent / "data"
LOG_FILE     = DATA_DIR / "download.log"
API_TIMEOUT  = 30
RATE_LIMIT   = 1.0   # seconds between requests

# ── Helpers ───────────────────────────────────────────────────────────────
def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(LOG_FILE.read_text() + line + "\n" if LOG_FILE.exists() else line + "\n")

def api_get(path, params=None):
    r = requests.get(f"{SLSKD_BASE}{path}", params=params, timeout=API_TIMEOUT)
    r.raise_for_status()
    return r.json()

def api_post(path, json=None):
    r = requests.post(f"{SLSKD_BASE}{path}", json=json, timeout=API_TIMEOUT)
    r.raise_for_status()
    return r.json()

def wait():
    time.sleep(RATE_LIMIT)

# ── Core actions ──────────────────────────────────────────────────────────
def search(query, limit=8):
    """Search Soulseek network. Returns list of file entries."""
    log(f"Recherche Soulseek : '{query}'")
    try:
        results = api_get("/api/search", params={"q": query, "limit": limit})
    except Exception as e:
        log(f"ERREUR search: {e}")
        return []

    files = results.get("files", []) or results.get("results", []) or []
    if not files:
        log("Aucun resultat.")
        return []

    # Pick the best quality (prefer mp3, largest file)
    def score(f):
        name = f.get("file", {}).get("filename", "") or f.get("filename", "") or ""
        size = f.get("file", {}).get("size", 0) or f.get("size", 0)
        ext  = name.lower().split(".")[-1] if "." in name else ""
        q    = 100 if ext == "mp3" else (50 if ext in {"flac", "wav", "m4a", "aac"} else 10)
        return q * 1_000_000 + size

    files.sort(key=score, reverse=True)
    return files[:limit]

def enqueue_download(file_entry, directory=None):
    """Enqueue a file for download. file_entry is a dict from search results."""
    # Normalize different slskd response formats
    f = file_entry.get("file", {}) or file_entry
    filename = f.get("filename", "") or file_entry.get("filename", "")
    size     = f.get("size", 0) or file_entry.get("size", 0)

    payload = {
        "filename": filename,
        "directory": str(directory) if directory else str(MUSIC_DIR),
    }

    # Add optional fields if present
    if " Bitrate" in filename or "bitrate" in f:
        payload["bitrate"] = f.get("bitrate")

    log(f"Enqueue: {filename} ({size // (1024*1024) if size else '?'} MB)")
    try:
        result = api_post("/api/downloads", json=payload)
        return result
    except Exception as e:
        log(f"ERREUR enqueue: {e}")
        return None

def download_status():
    """Return current download queue / active transfers."""
    try:
        return api_get("/api/downloads")
    except Exception as e:
        log(f"ERREUR status: {e}")
        return {}

# ── CLI ──────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Nova-Tunes downloader via slskd Soulseek API")
    p.add_argument("query", nargs="?", help="Search query (artist - title)")
    p.add_argument("--limit", "-n", type=int, default=8, help="Max results to search (default: 8)")
    p.add_argument("--all", "-a", action="store_true", help="Download all results instead of top 1")
    p.add_argument("--status", "-s", action="store_true", help="Show download queue")
    p.add_argument("--list", "-l", action="store_true", help="Search and list results only (no download)")
    args = p.parse_args()

    if args.status:
        print(json.dumps(download_status(), indent=2))
        return

    if not args.query:
        p.print_help()
        return

    files = search(args.query, limit=args.limit)
    if not files:
        return

    if args.list:
        print(f"\n  Resultats pour '{args.query}':\n")
        for i, f in enumerate(files, 1):
            fname = f.get("file", {}).get("filename", "") or f.get("filename", "")
            size  = f.get("file", {}).get("size", 0) or f.get("size", 0)
            mb    = size // (1024*1024)
            print(f"  [{i}] {fname}  ({mb} MB)")
        print()
        return

    to_download = files if args.all else [files[0]]

    for f in to_download:
        enqueue_download(f)
        wait()

    log(f"-> {len(to_download)} fichier(s) ajoute(s) a la queue.")
    print(f"\n  Telechargement en cours... verifie http://localhost:5030\n")

if __name__ == "__main__":
    main()
