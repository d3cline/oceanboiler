#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v python3 >/dev/null || { echo 'Python 3 is required.'; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod +x run.sh
echo
echo 'Ready: bash run.sh'
echo 'For Manjaro system audio dependencies, see README.md.'
