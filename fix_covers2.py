#!/usr/bin/env python3
"""Download missing covers using alternative methods."""

import urllib.request
import ssl
import json
from pathlib import Path

MUSIC = Path("/home/niko/nova-tunes/music")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

print("=== Alternative cover downloads ===\n")

# 1. Dark Tranquillity - Moment (2020) - try release-group endpoint
print("Dark Tranquillity/Moment (2020):")
mbid = "ebf0c28b-5dfd-495f-a345-ee95a9573420"
cover_path = MUSIC / "Dark Tranquillity/Moment (2020)" / "cover.jpg"

# Try release-group endpoint
for endpoint in ["front", "500"]:
    url = f"https://coverartarchive.org/release-group/{mbid}/{endpoint}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NovaTunes/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = r.read()
        if len(data) > 5000:
            cover_path.write_bytes(data)
            print(f"  ✓ Cover from release-group: {endpoint} ({len(data)//1024} KB)")
            break
    except Exception as e:
        print(f"  - release-group/{endpoint}: {e}")

# 2. Pink Floyd - Dark Side of the Moon - known iconic cover
print("\nPink Floyd/The Dark Side of the Moon (1973):")
mbid = "4534f168-c25e-4d84-9da6-4fb26a261640"
cover_path = MUSIC / "Pink Floyd/The Dark Side of the Moon (1973)" / "cover.jpg"

# Try release-group endpoint
for endpoint in ["front", "500"]:
    url = f"https://coverartarchive.org/release-group/{mbid}/{endpoint}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NovaTunes/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = r.read()
        if len(data) > 5000:
            cover_path.write_bytes(data)
            print(f"  ✓ Cover from release-group: {endpoint} ({len(data)//1024} KB)")
            break
    except Exception as e:
        print(f"  - release-group/{endpoint}: {e}")

# Fallback: direct Wikipedia URL for Dark Side of the Moon
if not cover_path.exists():
    print("  Trying Wikipedia fallback...")
    url = "https://upload.wikimedia.org/wikipedia/en/3/3b/Dark_Side_of_the_Moon.png"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NovaTunes/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = r.read()
        if len(data) > 5000:
            cover_path.write_bytes(data)
            print(f"  ✓ Cover from Wikipedia ({len(data)//1024} KB)")
    except Exception as e:
        print(f"  - Wikipedia failed: {e}")

print("\n=== Done ===")
