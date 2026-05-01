#!/usr/bin/env python3
"""Download Emperor - In The Nightside Eclipse (1994) via Soulseek."""

import urllib.request
import json
import ssl
import uuid
import time
import os
from pathlib import Path
from collections import defaultdict

MUSIC = Path("/home/niko/nova-tunes/music")
OUTPUT_DIR = MUSIC / "Emperor" / "In The Nightside Eclipse (1994)"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

SLSKD_BASE = "http://localhost:5030"
WEB_USER, WEB_PASS = "slskd", "slskd"

def get_token():
    req = urllib.request.Request(f"{SLSKD_BASE}/api/v0/session",
        data=json.dumps({"username": WEB_USER, "password": WEB_PASS}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=ctx) as r:
        return json.loads(r.read())["token"]

def search(token, query):
    search_id = str(uuid.uuid4())
    req = urllib.request.Request(f"{SLSKD_BASE}/api/v0/searches",
        data=json.dumps({"id": search_id, "searchText": query}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, context=ctx) as r:
        print(f"Search started: {json.loads(r.read())}")
    time.sleep(30)  # Wait for results
    req = urllib.request.Request(f"{SLSKD_BASE}/api/v0/searches/{search_id}/responses",
        headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, context=ctx) as r:
        results = json.loads(r.read())
    return results

def download_album(token, album_name, year):
    """Find and download album via Soulseek."""
    print(f"\n=== Searching for {album_name} ({year}) ===")
    
    # Search
    results = search(token, f"Emperor {album_name}")
    print(f"Found {len(results)} responses")
    
    # Group files by album directory
    album_files = defaultdict(list)  # key: (username, album_dir)
    
    for resp in results:
        username = resp.get("username", "")
        for f in resp.get("files", []):
            filename = f.get("filename", "")
            size = f.get("size", 0)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in (".flac", ".mp3", ".m4a"):
                continue
            # Check if file is part of the album
            parts = filename.replace("/", "\\").split("\\")
            # Find album folder in path
            for i, part in enumerate(parts):
                if album_name.lower() in part.lower() or "nightside" in part.lower():
                    album_dir = "\\".join(parts[:i+1])
                    album_files[(username, album_dir)].append((filename, size))
                    break
    
    # Find best album source (most files)
    best_key = max(album_files.keys(), key=lambda k: len(album_files[k])) if album_files else None
    if not best_key:
        print("No album found, trying broader search...")
        results = search(token, "Emperor In The Nightside Eclipse")
        # Fallback: collect all files with "nightside" or "emperor" in path
        # ... (simplified)
        return False
    
    username, album_dir = best_key
    files = album_files[best_key]
    print(f"\nBest source: {username}")
    print(f"Album dir: {album_dir}")
    print(f"Files: {len(files)}")
    for fn, sz in sorted(files)[:10]:
        print(f"  - {os.path.basename(fn)} ({sz//1024} KB)")
    
    # Enqueue download
    print(f"\nEnqueueing {len(files)} files from {username}...")
    dl_list = [{"filename": fn, "size": sz} for fn, sz in files]
    req = urllib.request.Request(f"{SLSKD_BASE}/api/v0/transfers/downloads/{username}",
        data=json.dumps(dl_list).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            resp_data = json.loads(r.read())
        if isinstance(resp_data, list):
            print(f"Enqueued {len(resp_data)} files")
        else:
            print(f"Response: {resp_data}")
    except Exception as e:
        print(f"Download enqueue error: {e}")
        return False
    
    # Monitor transfers
    print("\nMonitoring downloads (check docker logs for progress)...")
    # Wait a bit then check
    time.sleep(10)
    req = urllib.request.Request(f"{SLSKD_BASE}/api/v0/transfers/downloads",
        headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            transfers = json.loads(r.read())
        active = [t for t in transfers if t.get("state") not in ("Completed", "Cancelled")]
        print(f"Active downloads: {len(active)}")
        for t in active[:5]:
            print(f"  {os.path.basename(t.get('filename',''))}: {t.get('percentComplete',0):.1f}%")
    except Exception as e:
        print(f"Transfer check error: {e}")
    
    return True

def main():
    print("=== Emperor Album Download via Soulseek ===")
    token = get_token()
    print(f"Token obtained")
    
    success = download_album(token, "In The Nightside Eclipse", 1994)
    
    if success:
        print("\n=== Download initiated ===")
        print("Check docker logs -f soulseek for progress")
        print(f"Files will appear in: {OUTPUT_DIR}")
    else:
        print("\n=== Trying alternative: search for just 'Emperor' ===")
        results = search(token, "Emperor")
        print(f"Found {len(results)} responses for 'Emperor'")
        # Could process here...

if __name__ == "__main__":
    main()
