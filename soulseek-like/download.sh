#!/bin/bash
# Nova-Tunes download wrapper
# Tries slskd first (Soulseek P2P), falls back to yt-dlp
# Usage: ./download.sh "The Warning Error"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/download.py"
YTDLP="/home/niko/bin/yt-dlp"
MUSIC_DIR="$SCRIPT_DIR/../music"
LOG_FILE="$SCRIPT_DIR/../data/download.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE" 2>/dev/null || echo "$*"
}

# Check if slskd API is reachable
slskd_reachable() {
    curl -s --max-time 3 http://localhost:5030/api/search?q=test >/dev/null 2>&1
}

# ── Main ────────────────────────────────────────────────────────────────
if [[ $# -eq 0 ]]; then
    echo "Usage: $0 \"<requete>\""
    echo "Example: $0 \"The Warning Error\""
    exit 1
fi

QUERY="$1"
mkdir -p "$(dirname "$LOG_FILE")" "$MUSIC_DIR"

log "=== Download request: '$QUERY' ==="

if slskd_reachable; then
    log "-> Using slskd (Soulseek P2P)"
    python3 "$PYTHON_SCRIPT" "$QUERY"
else
    log "-> slskd unreachable, falling back to yt-dlp (YouTube)"
    if [[ ! -x "$YTDLP" ]]; then
        log "ERREUR: yt-dlp non trouve: $YTDLP"
        exit 1
    fi
    $YTDLP \
        --extract-audio \
        --audio-format mp3 \
        --audio-quality 0 \
        --output "$MUSIC_DIR/%(title)s.%(ext)s" \
        --metadata-from-title "%(artist)s - %(title)s" \
        "ytsearch10:$QUERY" \
        && log "OK: yt-dlp termine -> $MUSIC_DIR" \
        || { log "ERREUR: Echec yt-dlp pour: $QUERY"; exit 1; }
fi
