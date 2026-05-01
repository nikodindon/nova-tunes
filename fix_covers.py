#!/usr/bin/env python3
"""Download missing album covers from MusicBrainz Cover Art Archive."""

import urllib.request
import ssl
import json
import re
from pathlib import Path

MUSIC = Path("/home/niko/nova-tunes/music")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def search_mb_release(artist, album, year):
    """Search MusicBrainz for release ID."""
    query = f'release:"{album}" artist:"{artist}"'
    url = f"https://musicbrainz.org/ws/2/release/?query={urllib.parse.quote(query)}&fmt=json&limit=10"
    req = urllib.request.Request(url, headers={"User-Agent": "NovaTunes/1.0 (nikodindon@free.fr)"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = json.loads(r.read())
        for release in data.get("releases", []):
            release_date = str(release.get("date", ""))
            if year and str(year) in release_date:
                return release["id"], release_date
        # Fallback: return first result if year match fails
        if data.get("releases"):
            return data["releases"][0]["id"], data["releases"][0].get("date", "")
    except Exception as e:
        print(f"    MB search failed: {e}")
    return None, None

def download_cover(mbid, output_path):
    """Download cover from Cover Art Archive."""
    endpoints = ["front", "500", "250"]
    for endpoint in endpoints:
        try:
            url = f"https://coverartarchive.org/release/{mbid}/{endpoint}"
            req = urllib.request.Request(url, headers={"User-Agent": "NovaTunes/1.0 (nikodindon@free.fr)"})
            with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
                data = r.read()
            if len(data) > 5000:  # Minimum size check
                output_path.write_bytes(data)
                print(f"    ✓ Cover: {endpoint} ({len(data)//1024} KB)")
                return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue  # Try next endpoint
            print(f"    - HTTP {e.code}")
        except Exception as e:
            print(f"    - Failed: {e}")
    return False

def get_album_info(dir_name):
    """Extract album name and year from directory name."""
    # Patterns: "Album (2010)", "The Satanist (2014)", "Texas Flood (1983)"
    match = re.search(r'(.+?)\s*\((\d{4})\)', dir_name)
    if match:
        return match.group(1).strip(), int(match.group(2))
    return dir_name, None

# Main
print("=== Downloading missing covers ===\n")

albums_to_process = []

# Find all albums without covers
for artist in sorted(MUSIC.iterdir()):
    if not artist.is_dir():
        continue
    for album in sorted(artist.iterdir()):
        if not album.is_dir():
            continue
        cover = album / "cover.jpg"
        if cover.exists():
            continue
        tracks = list(album.glob("*.flac")) + list(album.glob("*.mp3"))
        if tracks:
            albums_to_process.append((artist.name, album.name, album))

for artist_name, album_name, album_path in albums_to_process:
    print(f"{artist_name}/{album_name}:")
    
    # Get album name and year from directory
    clean_name, year = get_album_info(album_name)
    
    # Search MusicBrainz
    mbid, release_date = search_mb_release(artist_name, clean_name, year)
    
    if mbid:
        print(f"  MBID: {mbid} ({release_date})")
        cover_path = album_path / "cover.jpg"
        if download_cover(mbid, cover_path):
            print(f"  ✓ Cover saved\n")
        else:
            print(f"  ✗ No cover found on Cover Art Archive\n")
    else:
        print(f"  ✗ No MusicBrainz match found\n")

print("=== Done ===")
