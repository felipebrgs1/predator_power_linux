#!/bin/bash
# Build script for Predator Power Manager single binary
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Generating embedded resources..."
python3 -c "
import base64

with open('tdp-manager.sh', 'r') as f:
    bash_content = f.read()
with open('auto-turbo-daemon.py', 'r') as f:
    daemon_content = f.read()
with open('tdp-manager-tui.py', 'r') as f:
    tui_content = f.read()

code = '# Auto-generated embedded resources\n\n'
code += f'BASH_SCRIPT = {repr(bash_content)}\n\n'
code += f'DAEMON_SCRIPT = {repr(daemon_content)}\n\n'
code += f'TUI_SCRIPT = {repr(tui_content)}\n'

with open('predator_pkg/resources.py', 'w') as f:
    f.write(code)
print('  resources.py OK')
"

echo "==> Building binary with PyInstaller..."
.venv/bin/pyinstaller \
    --onefile \
    --name predator-power \
    --hidden-import predator_pkg \
    --hidden-import predator_pkg.resources \
    --collect-all predator_pkg \
    predator-power.py

echo ""
echo "==> Build complete!"
echo "    Binary: $SCRIPT_DIR/dist/predator-power"
echo ""
echo "    Usage:"
echo "      ./dist/predator-power tui      # Launch TUI"
echo "      ./dist/predator-power status   # Show status"
echo "      ./dist/predator-power daemon   # Run daemon"
