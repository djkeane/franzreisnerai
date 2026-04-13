#!/usr/bin/env bash
# Franz auto-commit & push – változásokat 30 másodpercenként ellenőrzi
FRANZ_DIR="$HOME/Franz"
LOG="$FRANZ_DIR/logs/autopush.log"

mkdir -p "$FRANZ_DIR/logs"

cd "$FRANZ_DIR" || exit 1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Franz autopush indult" >> "$LOG"

while true; do
    sleep 30

    # Csak ha van változás (tracked fájlok)
    if ! git -C "$FRANZ_DIR" diff --quiet || ! git -C "$FRANZ_DIR" diff --cached --quiet; then
        MSG="auto: $(date '+%Y-%m-%d %H:%M:%S') – módosítások"
        git -C "$FRANZ_DIR" add -A
        git -C "$FRANZ_DIR" commit -m "$MSG" >> "$LOG" 2>&1
        git -C "$FRANZ_DIR" push origin main >> "$LOG" 2>&1
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Push OK: $MSG" >> "$LOG"
    fi
done
