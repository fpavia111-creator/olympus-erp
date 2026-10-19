#!/bin/sh
set -eu
cd "$(dirname "$0")"
PORT="${OLYMPUS_PORT:-8765}"
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Olympus needs Python 3.11 or newer. Install it (e.g. 'uv python install 3.11' or python.org) and re-run." >&2
  exit 1
fi
if [ ! -d .venv ]; then "$PY" -m venv .venv; fi
. .venv/bin/activate
python -m pip install -q -e ".[pdf]"
echo "Open http://127.0.0.1:$PORT in a browser on this computer (set OLYMPUS_PORT to change the port)."
olympus-web --workspace . --port "$PORT"
