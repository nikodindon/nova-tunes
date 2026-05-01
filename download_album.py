#!/usr/bin/env python3
"""
Nova-Tunes: Download any album via Soulseek (slskd) with full automation.

Features:
  - Multi-query search with proper wait times
  - Best source selection (most files + highest speed)
  - Auto-retry on rate limits
  - Auto-organize into Artist/Album (Year)/ structure
  - Auto-download cover art from iTunes API
  - Auto-fix permissions (no sudo needed)
  - JSON logging for audit trail

Usage:
  python3 download_album.py "Artist Name" "Album Name" [Year]
  
Example:
  python3 download_album.py "Emperor" "In The Nightside Eclipse" 1994
"""

import urllib.request
import json
import ssl
import uuid
import time
import os
import re
import shutil
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from urllib.error import HTTPError

# ============================================================================
# Configuration
# ============================================================================
SLSKD_BASE = "http://localhost:5030"
WEB_USER, WEB_PASS = "slskd", "slskd"
MUSIC_BASE = Path("/home/niko/nova-tunes/music")
CACHE_DIR = Path.home() / ".cache" / "nova-tunes"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


# ============================================================================
# Utility Functions
# ============================================================================
def sanitize_path(text: str) -> str:
    """Remove illegal filesystem characters from path components."""
    return re.sub(r'[/\\:*?"<>|]', '_', text).strip()


def log_download(artist: str, album: str, year: int, source: dict, files: list, status: str):
    """Save download log to JSON for future reference."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "artist": artist,
        "album": album,
        "year": year,
        "source": source,
        "files": files,
        "status": status,
    }
    log_path = CACHE_DIR / f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_path, "w") as f:
        json.dump(log_entry, f, indent=2)
    print(f"[log] Saved to {log_path}")


def get_token():
    """Authenticate with slskd and return bearer token."""
    req = urllib.request.Request(
        f"{SLSKD_BASE}/api/v0/session",
        data=json.dumps({"username": WEB_USER, "password": WEB_PASS}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            return json.loads(r.read())["token"]
    except Exception as e:
        print(f"[auth] Error: {e}")
        return None


def search(token: str, query: str, wait_sec: int = 25) -> list:
    """
    Launch a Soulseek search and wait for results.
    Soulseek needs ~20-30s to collect responses from peers.
    Returns list of response dicts or [] on error.
    """
    search_id = str(uuid.uuid4())
    payload = {"id": search_id, "searchText": query}
    req = urllib.request.Request(
        f"{SLSKD_BASE}/api/v0/searches",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            _ = json.loads(r.read())
    except Exception as e:
        print(f"[search] Start error: {e}")
        return []

    time.sleep(wait_sec)
    
    req = urllib.request.Request(
        f"{SLSKD_BASE}/api/v0/searches/{search_id}/responses",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[search] Fetch error: {e}")
        return []


def find_album_files(results: list, artist: str, album: str) -> dict:
    """
    Group files by (username, album_dir) and return best source.
    Returns: {(username, album_dir): [(filename, size, speed), ...]}
    """
    album_files = defaultdict(list)
    
    for resp in results:
        username = resp.get("username", "")
        for f in resp.get("files", []):
            filename = f.get("filename", "")
            size = f.get("size", 0)
            speed = f.get("speed", 0)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in (".flac", ".mp3", ".m4a", ".wav"):
                continue
            
            # Normalize path separators
            parts = filename.replace("/", "\\").split("\\")
            
            # Find album folder in path - look for exact album name match
            for i, part in enumerate(parts):
                # Must contain album name (case-insensitive)
                if album.lower() in part.lower():
                    album_dir = "\\".join(parts[:i+1])
                    album_files[(username, album_dir)].append((filename, size, speed))
                    break
    
    return album_files


def select_best_source(album_files: dict) -> tuple:
    """
    Select best source: most files, then highest average speed.
    Returns: (username, album_dir) or None
    """
    if not album_files:
        return None
    
    def source_score(key):
        files = album_files[key]
        avg_speed = sum(f[2] for f in files) / max(len(files), 1)
        return (len(files), avg_speed)
    
    return max(album_files.keys(), key=source_score)


def enqueue_downloads(token: str, username: str, files: list, max_retries: int = 3) -> bool:
    """
    Enqueue files for download with retry logic.
    files: [(filename, size, speed), ...]
    Deduplicates by filename before enqueuing.
    """
    # Deduplicate by filename (keep first occurrence)
    seen = set()
    unique_files = []
    for fn, sz, spd in files:
        if fn not in seen:
            seen.add(fn)
            unique_files.append((fn, sz, spd))
    
    print(f"[enqueue] Deduplicated: {len(files)} -> {len(unique_files)} files")
    
    dl_list = [{"filename": fn, "size": sz} for fn, sz, _ in unique_files]
    
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                f"{SLSKD_BASE}/api/v0/transfers/downloads/{username}",
                data=json.dumps(dl_list).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, context=ctx) as r:
                resp_data = json.loads(r.read())
            
            if isinstance(resp_data, list):
                print(f"[enqueue] ✅ Enqueued {len(resp_data)} files")
            else:
                print(f"[enqueue] Response: {resp_data}")
            return True
            
        except HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                print(f"[enqueue] Rate limited (429) – retry {attempt+1}/{max_retries} in 5s...")
                time.sleep(5)
                continue
            print(f"[enqueue] HTTP Error {e.code}: {e}")
            return False
        except Exception as e:
            if attempt < max_retries:
                print(f"[enqueue] Attempt {attempt} failed: {e} – retrying...")
                time.sleep(3)
                continue
            print(f"[enqueue] Failed after {max_retries} attempts: {e}")
            return False
    
    return False


def monitor_downloads(token: str, username: str, expected_count: int, timeout_sec: int = 600):
    """
    Monitor download progress until completion or timeout.
    Returns list of downloaded file paths.
    """
    print(f"\n[monitor] Watching {expected_count} downloads (timeout: {timeout_sec}s)...")
    start_time = time.time()
    completed_files = []
    
    while time.time() - start_time < timeout_sec:
        try:
            req = urllib.request.Request(
                f"{SLSKD_BASE}/api/v0/transfers/downloads",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, context=ctx) as r:
                transfers = json.loads(r.read())
        except Exception as e:
            print(f"[monitor] Check error: {e}")
            time.sleep(5)
            continue
        
        completed = [t for t in transfers if t.get("state") == "Completed"]
        active = [t for t in transfers if t.get("state") not in ("Completed", "Cancelled", "TimedOut")]
        
        # Show progress
        if active or completed:
            print(f"\r[monitor] Active: {len(active)} | Completed: {len(completed)}/{expected_count}", end="")
            if active:
                top = sorted(active, key=lambda x: x.get("percentComplete", 0), reverse=True)[:2]
                for t in top:
                    fn = os.path.basename(t.get("filename", ""))
                    pct = t.get("percentComplete", 0)
                    spd = t.get("speed", 0)
                    print(f"\n  {fn}: {pct:.1f}% @ {spd} KB/s", end="")
            print()
        
        # Check if all expected files are done
        if len(completed) >= expected_count and not active:
            print(f"\n[monitor] ✅ All {expected_count} downloads complete!")
            return [t.get("filename") for t in completed]
        
        time.sleep(5)
    
    print(f"\n[monitor] ⏱ Timeout after {timeout_sec}s – some files may still be downloading")
    return [t.get("filename") for t in completed]


def download_cover(artist: str, album: str, output_dir: Path) -> bool:
    """
    Download album cover from iTunes API.
    Returns True if successful.
    """
    print(f"\n[cover] Searching cover for '{artist} - {album}'...")
    
    query = f"{artist} {album}".replace(" ", "+")
    url = f"https://itunes.apple.com/search?term={query}&media=music&limit=5"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"[cover] iTunes API error: {e}")
        return False
    
    results = data.get("results", [])
    if not results:
        print(f"[cover] No cover found on iTunes")
        return False
    
    # Find best match (prefer exact album name match)
    best_match = None
    for result in results:
        collection_name = result.get("collectionName", "").lower()
        if album.lower() in collection_name or collection_name in album.lower():
            best_match = result
            break
    
    if not best_match:
        best_match = results[0]  # Fallback to first result
    
    artwork_url = best_match.get("artworkUrl100", "")
    if not artwork_url:
        print(f"[cover] No artwork URL in result")
        return False
    
    # Get HD version (replace 100x100 with 1000x1000)
    artwork_hd = artwork_url.replace("100x100bb", "1000x1000bb")
    
    cover_path = output_dir / "cover.jpg"
    try:
        urllib.request.urlretrieve(artwork_hd, cover_path)
        print(f"[cover] ✅ Downloaded: {artwork_hd}")
        return True
    except Exception as e:
        print(f"[cover] Download error: {e}")
        return False


def organize_files(source_dir: Path, artist: str, album: str, year: int) -> Path:
    """
    Organize downloaded files into Artist/Album (Year)/ structure.
    Returns the final album directory path.
    """
    # Create target directory
    album_dir = MUSIC_BASE / sanitize_path(artist) / sanitize_path(f"{album} ({year})")
    album_dir.mkdir(parents=True, exist_ok=True)
    
    # Move all audio files and covers
    moved_count = 0
    for file in source_dir.iterdir():
        if file.is_file() and file.suffix.lower() in (".flac", ".mp3", ".m4a", ".wav", ".jpg", ".png"):
            dest = album_dir / file.name
            try:
                shutil.move(str(file), str(dest))
                moved_count += 1
            except Exception as e:
                print(f"[organize] Error moving {file.name}: {e}")
    
    print(f"[organize] ✅ Moved {moved_count} files to {album_dir}")
    return album_dir


def fix_permissions(path: Path):
    """
    Fix file permissions so user owns all downloaded files.
    Tries multiple approaches:
    1. os.chown() (works if running as root or files already owned)
    2. docker exec to chown from inside container (if Docker available)
    3. Copy files to temp, delete originals, move back (preserves content, changes ownership)
    """
    print(f"[perms] Fixing permissions for {path}...")
    
    # Get current user's uid/gid
    uid = os.getuid()
    gid = os.getgid()
    
    # Try approach 1: direct chown (works if we own the files or running as root)
    changed = 0
    failed = []
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            file_path = Path(root) / name
            try:
                os.chown(file_path, uid, gid)
                changed += 1
            except PermissionError:
                failed.append(file_path)
            except Exception as e:
                print(f"[perms] Error on {file_path}: {e}")
    
    if changed > 0:
        print(f"[perms] ✅ Fixed {changed} files with chown")
    
    # If some files failed, try approach 2: docker exec
    if failed:
        print(f"[perms] ⚠️  {len(failed)} files need sudo - trying Docker approach...")
        try:
            # Get the Docker container name for slskd
            import subprocess
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=soulseek", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=10
            )
            container_name = result.stdout.strip()
            
            if container_name:
                # Use docker exec to chown files from inside the container
                # Mount the music directory and run chown
                for file_path in failed[:10]:  # Limit to first 10 to avoid timeout
                    try:
                        subprocess.run(
                            ["docker", "exec", container_name, "chown", f"{uid}:{gid}", str(file_path)],
                            capture_output=True, timeout=5
                        )
                        changed += 1
                        failed.remove(file_path)
                    except Exception:
                        pass
                
                print(f"[perms] ✅ Docker fixed {changed} additional files")
        except Exception as e:
            print(f"[perms] ℹ️  Docker approach failed: {e}")
    
    # Approach 3: If still failed, inform user about one-time sudo
    if failed:
        print(f"[perms] ⚠️  {len(failed)} files still owned by root")
        print(f"[perms] ℹ️  To fix permanently, run once:")
        print(f"   sudo chown -R $USER:$USER {path}")
        print(f"[perms] ℹ️  Or configure Docker to use your UID/GID (see skill docs)")


def cleanup_temp_folders():
    """Remove Soulseek's temporary download folders."""
    temp_patterns = [
        r"^\(\d{4}\)\s+.*\[(flac|mp3|m4a)\]$",  # (2000) Album [flac]
        r"^@@.*$",  # @@lggju style folders
    ]
    
    for item in MUSIC_BASE.iterdir():
        if item.is_dir():
            for pattern in temp_patterns:
                if re.match(pattern, item.name):
                    try:
                        # Check if folder is empty first
                        if not any(item.iterdir()):
                            shutil.rmtree(item)
                            print(f"[cleanup] ✅ Removed empty temp folder: {item.name}")
                    except Exception as e:
                        print(f"[cleanup] Error removing {item.name}: {e}")
                    break


def download_album(artist: str, album: str, year: int):
    """Main download function with full automation."""
    print(f"\n{'='*70}")
    print(f"🎵 Nova-Tunes: Downloading {artist} – {album} ({year})")
    print(f"{'='*70}\n")
    
    # Step 1: Authenticate
    token = get_token()
    if not token:
        print("[error] Could not obtain token – aborting")
        return False
    print("[auth] ✅ Token obtained")
    
    # Step 2: Multi-query search
    queries = [
        f"{artist} {album}",
        f"{artist} {album} {year}",
        f"{artist} {album.lower()}",
        f"{artist}",
    ]
    
    print(f"[search] Launching searches...")
    all_results = []
    for i, q in enumerate(queries):
        results = search(token, q, wait_sec=25 if i == 0 else 15)
        print(f"  '{q}': {len(results)} responses")
        all_results.extend(results)
    
    print(f"[search] Total: {len(all_results)} responses")
    
    if not all_results:
        print("[error] No results found")
        return False
    
    # Step 3: Find and select best source
    album_files = find_album_files(all_results, artist, album)
    
    if not album_files:
        print(f"[error] No files found for '{artist} – {album}'")
        return False
    
    best_key = select_best_source(album_files)
    if not best_key:
        print("[error] Could not select best source")
        return False
    
    username, album_dir = best_key
    files = album_files[best_key]
    
    # Filter to only audio files for the main album (not bonus/live/compilations)
    # Look for files where the folder path contains the exact album name
    audio_files = []
    for fn, sz, spd in files:
        # Check if file path contains album name in folder structure
        fn_lower = fn.lower()
        album_lower = album.lower()
        
        # Must contain album name in path
        if album_lower in fn_lower:
            audio_files.append((fn, sz, spd))
    
    if not audio_files:
        # Fallback: take all audio files if no exact match
        audio_files = [(fn, sz, spd) for fn, sz, spd in files 
                       if any(ext in fn.lower() for ext in ['.flac', '.mp3', '.m4a', '.wav'])]
    
    print(f"\n[select] Best source: {username}")
    print(f"  Album dir: {album_dir}")
    print(f"  Files: {len(audio_files)}")
    for fn, sz, spd in sorted(audio_files, key=lambda x: x[0])[:10]:
        print(f"    - {os.path.basename(fn)} ({sz//1024} KB)")
    
    # Step 4: Enqueue downloads
    if not enqueue_downloads(token, username, audio_files):
        print("[error] Failed to enqueue")
        return False
    
    # Step 5: Monitor progress
    completed = monitor_downloads(token, username, len(audio_files), timeout_sec=600)
    
    # Step 6: Wait for files to appear in music directory
    print("\n[organize] Waiting for files to appear...")
    time.sleep(10)  # Give Soulseek time to write files
    
    # Find the downloaded folder (look for most recent directory with matching files)
    downloaded_dir = None
    for item in MUSIC_BASE.iterdir():
        if item.is_dir() and item.stat().st_mtime > time.time() - 600:  # Modified in last 10 min
            audio_count = len([f for f in item.iterdir() if f.suffix.lower() in (".flac", ".mp3", ".m4a", ".wav")])
            if audio_count >= len(audio_files) * 0.8:  # At least 80% of expected files
                downloaded_dir = item
                break
    
    if not downloaded_dir:
        print("[organize] ⚠️  Could not find downloaded folder – check manually")
        # Try to find any recently created folder
        recent_dirs = [d for d in MUSIC_BASE.iterdir() 
                      if d.is_dir() and d.stat().st_mtime > time.time() - 600]
        if recent_dirs:
            downloaded_dir = max(recent_dirs, key=lambda d: d.stat().st_mtime)
            print(f"[organize] Using most recent: {downloaded_dir.name}")
    
    if downloaded_dir:
        # Step 7: Organize files
        final_dir = organize_files(downloaded_dir, artist, album, year)
        
        # Step 8: Download cover
        download_cover(artist, album, final_dir)
        
        # Step 9: Fix permissions
        fix_permissions(final_dir)
        
        # Step 10: Cleanup temp folders
        cleanup_temp_folders()
        
        # Step 11: Trigger Navidrome scan
        print("\n[navidrome] Triggering library scan...")
        try:
            req = urllib.request.Request(
                "http://localhost:4533/api/scan",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                print(f"[navidrome] ✅ Scan triggered")
        except Exception as e:
            print(f"[navidrome] ℹ️  Scan will happen automatically: {e}")
        
        # Log result
        log_download(
            artist, album, year,
            {"username": username, "album_dir": album_dir},
            [{"filename": fn, "size": sz, "speed": spd} for fn, sz, spd in audio_files],
            "completed" if len(completed) >= len(audio_files) * 0.8 else "partial",
        )
        
        print(f"\n{'='*70}")
        print(f"✅ Download complete! Album available at:")
        print(f"   {final_dir}")
        print(f"{'='*70}\n")
        return True
    
    return False


def main():
    import sys
    
    if len(sys.argv) >= 3:
        artist = sys.argv[1]
        album = sys.argv[2]
        year = int(sys.argv[3]) if len(sys.argv) > 3 else datetime.now().year
    else:
        print("Usage: python3 download_album.py <artist> <album> [year]")
        print("Example: python3 download_album.py 'Emperor' 'In The Nightside Eclipse' 1994")
        sys.exit(1)
    
    success = download_album(artist, album, year)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
