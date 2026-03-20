#!/usr/bin/env python3
"""Generate embedded resources module for PyInstaller."""

import os

pkg_dir = os.path.join(os.path.dirname(__file__), "predator_pkg")
os.makedirs(pkg_dir, exist_ok=True)

bash = open("tdp-manager.sh").read()
daemon = open("auto-turbo-daemon.py").read()
tui = open("tdp-manager-tui.py").read()

with open(os.path.join(pkg_dir, "resources.py"), "w") as f:
    f.write("# Auto-generated\n\n")
    f.write(f"BASH_SCRIPT = {repr(bash)}\n\n")
    f.write(f"DAEMON_SCRIPT = {repr(daemon)}\n\n")
    f.write(f"TUI_SCRIPT = {repr(tui)}\n")

print("resources.py OK")
