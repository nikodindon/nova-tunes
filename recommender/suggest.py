#!/usr/bin/env python3
"""
Nova-Tunes Recommender v7 (final)
"""

import sys, json, argparse, time
from pathlib import Path
from collections import Counter

import musicbrainzngs
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

MUSIC_DIR = Path(__file__).parent.parent / "music"
DATA_DIR  = Path(__file__).parent.parent / "data"
LIB_CACHE = DATA_DIR / "library_cache.json"
RATE     = 0.55

musicbrainzngs.set_useragent("Nova-Tunes", "0.1", "nikotunes@example.com")

BLACKLIST = {"various artists", "various", "[unknown]", "unknown", ""}
# Tags qui ramenent du bruit / suggestions trop generiques
SKIP_TAGS = {
    "rock", "metal", "music", "american", "british",
    "classic rock", "hard rock", "rock music",
    "blues rock", "pop rock", "psychedelic rock",
    "glam rock", "new wave", "post-punk",
    "heavy metal", "speed metal", "alternative rock",
}

def is_good_name(name):
    """Reject names that are too short, too generic, or duplicated words."""
    n = name.lower()
    if n in BLACKLIST:
        return False
    if len(name) < 3:
        return False
    # reject "X X" where both words are the same (e.g. "metal metal")
    parts = n.split()
    if len(parts) >= 2 and parts[0] == parts[-1]:
        return False
    return True

def mb(q, limit=6):
    for attempt in range(3):
        try:
            time.sleep(RATE)
            return musicbrainzngs.search_artists(q, limit=limit)
        except Exception:
            if attempt < 2: time.sleep(1)
    return {}

def artist_info(name):
    r = mb(name, limit=5)
    for a in r.get("artist-list", []):
        if int(a.get("ext:score", 0)) >= 90:
            mbid = a["id"]
            area = a.get("area", {}).get("name", "")
            try:
                time.sleep(RATE)
                info = musicbrainzngs.get_artist_by_id(mbid, includes=["tags"])
                tags = info["artist"].get("tag-list", [])
                tags.sort(key=lambda x: int(x.get("count", 0)), reverse=True)
                return mbid, [t["name"] for t in tags[:6]], area
            except Exception:
                return mbid, [], area
    return None, [], ""

def add_suggestions(q, mbid, seen, suggestions, max_res=5, min_score=75):
    r = mb(q, limit=12)
    for a in r.get("artist-list", []):
        sname = a.get("name", "")
        score = int(a.get("ext:score", 0))
        if score < min_score:
            continue
        if not is_good_name(sname):
            continue
        if sname.lower() in seen:
            continue
        suggestions.append(sname)
        seen.add(sname.lower())
        if len(suggestions) >= max_res:
            break

def find_similar(name):
    mbid, tags, area = artist_info(name)
    if not mbid:
        return [], tags

    suggestions = []
    seen = {name.lower(), mbid.lower()}

    # Tags specifiques (pas dans SKIP_TAGS)
    specific = [t for t in tags if t not in SKIP_TAGS]
    if not specific:
        specific = [t for t in tags if t not in {"rock", "metal"}]
    if not specific:
        specific = tags[:2]

    # S1: tag specifique, exclut l'artiste
    for tag in specific[:2]:
        add_suggestions(f"tag:{tag} AND NOT arid:{mbid}", mbid, seen, suggestions, max_res=6, min_score=75)
        if len(suggestions) >= 5:
            break

    # S2: tag + pays (groupes regionaux)
    if len(suggestions) < 4 and area:
        tag = specific[0] if specific else "metal"
        add_suggestions(f"tag:{tag} AND area:{area}", mbid, seen, suggestions, max_res=6, min_score=70)

    # S3: autres tags dispo
    if len(suggestions) < 3:
        for tag in (specific[2:5] if len(specific) > 2 else tags[2:5]):
            add_suggestions(f"tag:{tag}", mbid, seen, suggestions, max_res=5, min_score=78)
            if len(suggestions) >= 3:
                break

    return suggestions[:6], tags

# ── Library ────────────────────────────────────────────────────────────
def extract_library():
    if LIB_CACHE.exists():
        return json.loads(LIB_CACHE.read_text())
    tracks = []
    for fp in sorted(MUSIC_DIR.rglob("*.mp3")):
        try:
            a = MP3(str(fp), ID3=EasyID3)
            artist = a.get("artist", [fp.parent.name])[0].strip()
            album  = a.get("album",  [fp.parent.name])[0].strip()
            title  = a.get("title",  [fp.stem])[0].strip()
            year   = a.get("date",  [""])[0][:4].strip()
        except Exception:
            artist, album, title, year = fp.parent.name, fp.parent.parent.name, fp.stem, ""
        if not artist or artist.lower() in BLACKLIST:
            artist = fp.parent.name or "Unknown"
        tracks.append({"artist": artist, "album": album, "title": title, "year": year, "path": str(fp)})
    LIB_CACHE.write_text(json.dumps({"tracks": tracks}, indent=2))
    return {"tracks": tracks}

def top_artists(library, n=5):
    artists = [t["artist"] for t in library["tracks"] if t["artist"].lower() not in BLACKLIST]
    return [a for a, _ in Counter(artists).most_common(n)]

def build():
    lib  = extract_library()
    tops = top_artists(lib)
    results = []
    for artist in tops:
        if not artist or artist.lower() in BLACKLIST:
            continue
        print(f"  Analyse de '{artist}'...", file=sys.stderr, flush=True)
        sim, tags = find_similar(artist)
        results.append({"artist": artist, "tags": tags, "similar": sim})
        if len(results) >= 3:
            break
    return results

def display(results):
    sep = "=" * 52
    print()
    print(f"  {sep}")
    print(f"  ||        NOVA-TUNES  --  SUGGESTIONS              ||")
    print(f"  {sep}")
    print()
    if not results:
        print("  [x] Pas assez de donnees. Ajoute de la musique d'abord !")
        return
    for i, r in enumerate(results, 1):
        tags_str = ", ".join(r["tags"][:5]) if r["tags"] else "rock / metal"
        print(f"  [{i}] {r['artist']}")
        print(f"      Style : {tags_str}")
        if r["similar"]:
            print(f"      Groupe similaires : {', '.join(r['similar'])}")
        print()
    print(f"  -> Telecharge via Soulseek : http://localhost:6080")
    print(f"     puis relance : python3 recommender/suggest.py --refresh")
    print(f"  {sep}")
    print()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--artist", "-a")
    p.add_argument("--refresh", "-r", action="store_true")
    args = p.parse_args()
    if args.refresh and LIB_CACHE.exists():
        LIB_CACHE.unlink()
    if args.artist:
        sim, tags = find_similar(args.artist)
        display([{"artist": args.artist, "tags": tags, "similar": sim}])
    else:
        display(build())
