#!/usr/bin/env bash
# Opens an interactive FDL2 prompt. There are deliberately no flash/reset commands.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_SAVE="${1:-$TASK_ROOT/work/session}"
mkdir -p -- "$TASK_SAVE"
TASK_SAVE="$(cd -- "$TASK_SAVE" && pwd)"
if [[ "$TASK_ROOT" =~ [[:space:]] || "$TASK_SAVE" =~ [[:space:]] ]]; then
  echo 'Use paths without whitespace for the old spd_dump interactive parser.' >&2
  exit 1
fi
python3 "$TASK_ROOT/scripts/k70.py" check-tools
exec sudo "$TASK_ROOT/work/tools/spreadtrum_flash/spd_dump" --wait 180 \
  fdl "$TASK_ROOT/work/tools/fdl1-dl.bin" 0x5500 \
  fdl "$TASK_ROOT/work/tools/fdl2-dl.bin" 0x9efffe00 \
  exec path "$TASK_SAVE"
