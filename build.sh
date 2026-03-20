#!/bin/bash
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> Generating resources..."
python3 gen_resources.py

echo "==> Building binary..."
.venv/bin/pyinstaller \
    --onefile \
    --name predator-power \
    --hidden-import curses \
    --hidden-import predator_pkg \
    --hidden-import predator_pkg.resources \
    --collect-all predator_pkg \
    predator-power.py

echo ""
echo "==> Done: dist/predator-power"
