#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Run: bash install.sh'
  exit 1
fi
# Qt compatibility: avoid the reported Wayland text-input focus issue.
# Override with QT_QPA_PLATFORM=wayland if your desktop has no XWayland.
if [[ -n "${DISPLAY:-}" ]]; then
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
fi
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export PIPEWIRE_LATENCY="${PIPEWIRE_LATENCY:-256/48000}"
export PIPEWIRE_PROPS="${PIPEWIRE_PROPS:-{ node.name = Oceanboiler node.description = Oceanboiler }}"
if command -v pw-jack >/dev/null 2>&1; then
  exec pw-jack .venv/bin/python app.py "$@"
fi
exec .venv/bin/python app.py "$@"
