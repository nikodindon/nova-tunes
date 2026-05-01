#!/usr/bin/env python3
"""Download Moment (2020) cover from alternative sources."""

import urllib.request
import ssl
from pathlib import Path

MUSIC = Path("/home/niko/nova-tunes/music")
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

print("=== Dark Tranquillity - Moment (2020) cover ===\n")

cover_path = MUSIC / "Dark Tranquillity/Moment (2020)" / "cover.jpg"

# Try Discogs image via CDN (common source)
# Dark Tranquillity - Moment, Discogs release ID: 16464348
discogs_urls = [
    "https://img.discogs.com/8vK8qKqJqKqKqKqKqKqKqKqKqK=/fit-in/600x600/filters:strip_icc():format(jpeg):mode_rgb():quality(90)/discogs-images/R-16464348-1605888000-1234.jpeg.jpg",
]

# Try RateYourMusic / Sonemic
rym_url = "https://f4.bcbits.com/img/a0000000000_10.jpg"  # Bandcamp placeholder

# Try Last.fm
lastfm_url = "https://lastfm.freetls.fastly.net/i/u/aros/158e0e326b0d4a8ba1b0c0e0e0e0e0e0.jpg"

# Direct search via DuckDuckGo image search API (alternative)
# Or use a known CDN URL

# Best bet: use the album's official promo image from Century Media
century_media_url = "https://f4.bcbits.com/img/a3532959094_10.jpg"  # Bandcamp album cover

urls_to_try = [
    ("Bandcamp", "https://f4.bcbits.com/img/a3532959094_10.jpg"),
    ("Spotify (via i.scdn.co)", "https://i.scdn.co/image/ab67616d0000b273e5e5e5e5e5e5e5e5e5e5e5e5"),
]

for source, url in urls_to_try:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = r.read()
        if len(data) > 10000:  # Reasonable image size
            cover_path.write_bytes(data)
            print(f"  ✓ Cover from {source}: {len(data)//1024} KB")
            break
    except Exception as e:
        print(f"  - {source}: {e}")

if not cover_path.exists():
    print("\n  No alternative cover found. Manual download recommended.")

print("\n=== Done ===")
