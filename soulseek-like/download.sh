#!/bin/bash
# soulseek-like/download.sh
# Télécharge de la musique via yt-dlp (FMA, Jamendo, YouTube, etc.)
# Usage: ./download.sh "The Warning Error"

set -euo pipefail

YTDLP="/home/niko/bin/yt-dlp"

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 \"<requête de recherche>\""
  echo "Example: $0 \"The Warning Error\""
  exit 1
fi

QUERY="$1"
MUSIC_DIR="$(dirname "$(realpath "$0")")/../music"
LOG_FILE="$(dirname "$(realpath "$0")")/../data/download.log"

mkdir -p "$MUSIC_DIR" "$(dirname "$LOG_FILE")"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "Recherche : '$QUERY'"

if [[ ! -x "$YTDLP" ]]; then
  log "ERREUR: yt-dlp non trouvé. Installe-le :"
  log "  curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /home/niko/bin/yt-dlp"
  log "  chmod a+rx /home/niko/bin/yt-dlp"
  exit 1
fi

log "Telechargement en cours..."
$YTDLP \
  --extract-audio \
  --audio-format mp3 \
  --audio-quality 0 \
  --output "$MUSIC_DIR/%(title)s.%(ext)s" \
  --metadata-from-title "%(artist)s - %(title)s" \
  "ytsearch10:$QUERY" \
  && log "OK: Telechargement termine -> $MUSIC_DIR" \
  || { log "ERREUR: Echec du telechargement pour : $QUERY"; exit 1; }
