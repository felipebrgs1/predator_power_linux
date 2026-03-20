#!/usr/bin/env python3
"""Predator Power Manager - Single Binary"""

import sys
import os
import subprocess
import tempfile


def _write_temp(content, name):
    tmpdir = tempfile.mkdtemp(prefix="predator_")
    path = os.path.join(tmpdir, name)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o755)
    return path, tmpdir


def run_bash(args):
    from predator_pkg.resources import BASH_SCRIPT

    path, tmpdir = _write_temp(BASH_SCRIPT, "tdp-manager.sh")
    try:
        # If installing service, pass the current binary path so the service is permanent
        if args and args[0] == "service" and "remove" not in args:
            binary_path = os.path.abspath(sys.executable)
            args = list(args) + [binary_path]

        cmd = [path] + args
        if os.getuid() != 0:
            cmd = ["pkexec"] + cmd
        return subprocess.run(cmd, text=True).returncode
    finally:
        try:
            os.unlink(path)
            os.rmdir(tmpdir)
        except OSError:
            pass


def run_tui():
    from predator_pkg.resources import BASH_SCRIPT, TUI_SCRIPT

    path, tmpdir = _write_temp(BASH_SCRIPT, "tdp-manager.sh")
    try:
        g = globals().copy()
        g["BASH_SCRIPT_PATH"] = path
        exec(compile(TUI_SCRIPT, "tdp-manager-tui.py", "exec"), g)
    finally:
        try:
            os.unlink(path)
            os.rmdir(tmpdir)
        except OSError:
            pass


def run_daemon():
    from predator_pkg.resources import DAEMON_SCRIPT

    exec(compile(DAEMON_SCRIPT, "auto-turbo-daemon.py", "exec"), globals())


HELP = """
Predator Power Manager
======================

Usage: predator-power [COMMAND] [ARGS]

Commands:
  tui              Launch interactive TUI (default)
  status           Show current power config
  set PL1 PL2      Set custom power limits (watts)
  profile NAME     Apply profile (balanced|performance|turbo)
  fanboost 0|1     Toggle fan boost
  list             List profiles
  service          Install boot service
  service remove   Remove boot service
  help             Show this help
"""

CMDS = ("status", "set", "profile", "list", "fanboost", "service")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tui"

    if cmd == "tui":
        run_tui()
    elif cmd == "daemon":
        run_daemon()
    elif cmd in ("help", "-h", "--help"):
        print(HELP)
    elif cmd in CMDS:
        sys.exit(run_bash(sys.argv[1:]))
    else:
        print(f"Unknown: {cmd}")
        print(HELP)
        sys.exit(1)


if __name__ == "__main__":
    main()
