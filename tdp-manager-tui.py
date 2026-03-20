#!/usr/bin/env python3
"""Predator Power Manager - Simple TUI"""

import curses
import subprocess
import os
import threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Check if provided via global from predator-power.py
SCRIPT = globals().get("BASH_SCRIPT_PATH", os.path.join(SCRIPT_DIR, "tdp-manager.sh"))
RAPL = "/sys/class/powercap/intel-rapl/intel-rapl:0"
FAN_PATH = "/sys/devices/platform/acer-thermal-lite/fan_boost"


def get_auth():
    return [] if os.getuid() == 0 else ["pkexec"]


def read_rapl(n):
    try:
        with open(f"{RAPL}/constraint_{n}_power_limit_uw") as f:
            return int(f.read().strip()) // 1000000
    except (OSError, ValueError):
        return 0


def read_fan():
    try:
        with open(FAN_PATH) as f:
            return f.read().strip() == "1"
    except OSError:
        return False


def service_active():
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "predator-power"], capture_output=True, text=True
        )
        return r.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


def run(args):
    subprocess.run(
        get_auth() + [SCRIPT] + args, capture_output=True, text=True, timeout=10
    )


class TUI:
    def __init__(self, scr):
        self.scr = scr
        self.running = True
        self.msg = ""
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.curs_set(0)
        scr.nodelay(True)
        scr.timeout(500)

    def draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        pl1, pl2 = read_rapl(0), read_rapl(1)
        fan = read_fan()
        svc = service_active()
        cx = max((w - 34) // 2, 1)

        y = 1
        self.scr.addstr(
            y, (w - 20) // 2, "Predator Power", curses.color_pair(1) | curses.A_BOLD
        )
        y += 2

        self.scr.addstr(y, cx, f"  PL1: {pl1}W    PL2: {pl2}W", curses.color_pair(2))
        y += 1
        self.scr.addstr(
            y,
            cx,
            f"  Fan Boost: {'ON' if fan else 'OFF'}",
            curses.color_pair(2) if fan else curses.color_pair(3),
        )
        y += 1
        self.scr.addstr(
            y,
            cx,
            f"  Auto Service: {'ON' if svc else 'OFF'}",
            curses.color_pair(2) if svc else curses.color_pair(3),
        )
        y += 2

        items = [
            ("1", "Balanced   50W/65W"),
            ("2", "Performance 80W/115W"),
            ("3", "Turbo    100W/140W"),
            ("", ""),
            ("F", "Toggle Fan Boost"),
            ("S", "Toggle Auto Service"),
            ("R", "Refresh"),
            ("Q", "Quit"),
        ]

        for key, label in items:
            if key == "":
                y += 1
                continue
            self.scr.addstr(y, cx, f"  [{key}] {label}", curses.color_pair(1))
            y += 1

        if self.msg:
            self.scr.addstr(
                h - 1,
                max((w - len(self.msg)) // 2, 0),
                self.msg,
                curses.color_pair(2) | curses.A_BOLD,
            )
        self.scr.refresh()

    def handle(self, key):
        profiles = {
            ord("1"): "balanced",
            ord("2"): "performance",
            ord("3"): "turbo",
        }

        if key in profiles:
            p = profiles[key]

            def task_p():
                run(["profile", p])
                self.msg = f"Profile: {p.upper()}"

            threading.Thread(target=task_p, daemon=True).start()
            self.msg = f"Applying {p}..."
        elif key == ord("f") or key == ord("F"):
            fan = read_fan()
            state = "0" if fan else "1"

            def task_f():
                run(["fanboost", state])
                self.msg = f"Fan Boost: {'ON' if state == '1' else 'OFF'}"

            threading.Thread(target=task_f, daemon=True).start()
            self.msg = "Toggling fan..."
        elif key == ord("s") or key == ord("S"):
            svc = service_active()
            cmd = ["service", "remove"] if svc else ["service", "balanced"]

            def task_s():
                run(cmd)
                self.msg = "Service Updated"

            threading.Thread(target=task_s, daemon=True).start()
            self.msg = "Toggling service..."
        elif key == ord("r") or key == ord("R"):
            self.msg = "Refreshed"
        elif key == ord("q") or key == ord("Q"):
            self.running = False

    def run(self):
        while self.running:
            self.draw()
            try:
                k = self.scr.getch()
                if k != -1:
                    self.handle(k)
            except (KeyboardInterrupt, curses.error):
                self.running = False


def main(scr):
    TUI(scr).run()


if __name__ == "__main__":
    curses.wrapper(main)
