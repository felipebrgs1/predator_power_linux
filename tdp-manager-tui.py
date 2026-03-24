#!/usr/bin/env python3
"""Predator Power Manager - Enhanced TUI"""

import curses
import subprocess
import os
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT = globals().get("BASH_SCRIPT_PATH", os.path.join(SCRIPT_DIR, "tdp-manager.sh"))
RAPL = "/sys/class/powercap/intel-rapl/intel-rapl:0"
FAN_PATH = "/sys/devices/platform/acer-thermal-lite/fan_boost"
CONFIG_FILE = "/tmp/predator_profile"

PROFILES = {
    "balanced": {"pl1": 50, "pl2": 65, "desc": "Balanced", "color": 3},
    "performance": {"pl1": 80, "pl2": 115, "desc": "Performance", "color": 4},
    "turbo": {"pl1": 100, "pl2": 140, "desc": "Turbo", "color": 2},
}

AUTH = [] if os.getuid() == 0 else ["pkexec"]


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


def read_current_profile():
    try:
        with open(CONFIG_FILE) as f:
            return f.read().strip()
    except OSError:
        return "balanced"


def service_active():
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "predator-power"], capture_output=True, text=True
        )
        return r.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


def run(args):
    subprocess.run(AUTH + [SCRIPT] + args, capture_output=True, text=True, timeout=10)


def get_system_info():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":")[1].strip()
    except:
        pass
    return "Unknown CPU"


class TUI:
    def __init__(self, scr):
        self.scr = scr
        self.running = True
        self.msg = ""
        self.msg_time = 0
        self.pl1, self.pl2 = 0, 0
        self.fan = False
        self.svc = False
        self.current_profile = "balanced"
        self.cpu_name = get_system_info()
        self.anim_frame = 0
        self.start_time = time.time()

        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_MAGENTA, -1)
        curses.init_pair(5, curses.COLOR_CYAN, -1)
        curses.init_pair(6, curses.COLOR_RED, -1)
        curses.init_pair(7, 8, -1)
        curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.curs_set(0)
        scr.nodelay(True)
        scr.timeout(100)

    def draw_bar(self, y, x, width, filled, color_pair, label=""):
        bar_width = width - len(label) - 2
        fill_width = int(bar_width * filled)
        bar = "█" * fill_width + "░" * (bar_width - fill_width)
        self.scr.addstr(y, x, f"[{bar}] {label}", color_pair)

    def get_cpu_usage_indicator(self):
        return ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"][self.anim_frame % 10]

    def draw_header(self, h, w):
        cy = 1
        title = " PREDATOR POWER MANAGER "
        self.scr.attron(curses.color_pair(5) | curses.A_BOLD)
        self.scr.addstr(cy, (w - len(title)) // 2, title)
        self.scr.attroff(curses.color_pair(5) | curses.A_BOLD)

        cy += 1
        line = "═" * (w - 4)
        self.scr.attron(curses.color_pair(7))
        self.scr.addstr(cy, 2, line)
        self.scr.attroff(curses.color_pair(7))

        return cy + 1

    def draw_status(self, h, w, start_y):
        cx = max(w // 2 - 24, 2)

        self.scr.addstr(start_y, cx, "┌─ System Status ─┐", curses.color_pair(7))
        y = start_y + 1

        cpu_short = self.cpu_name[:40] if len(self.cpu_name) > 40 else self.cpu_name
        self.scr.addstr(y, cx, f"│ CPU: {cpu_short:<36} │", curses.color_pair(1))
        y += 1
        self.scr.addstr(
            y,
            cx,
            f"│ Profile: {self.current_profile:<30} │",
            curses.color_pair(PROFILES.get(self.current_profile, {}).get("color", 1))
            | curses.A_BOLD,
        )
        y += 2

        self.scr.addstr(y, cx, "└" + "─" * 49 + "┘", curses.color_pair(7))
        return y + 1

    def draw_power(self, h, w, start_y):
        cx = max(w // 2 - 24, 2)

        self.scr.addstr(start_y, cx, "┌─ Power Limits ─┐", curses.color_pair(7))
        y = start_y + 1

        pl1_pct = min(self.pl1 / 140.0, 1.0)
        pl2_pct = min(self.pl2 / 140.0, 1.0)

        pl1_color = (
            curses.color_pair(2)
            if self.pl1 >= 80
            else curses.color_pair(3)
            if self.pl1 >= 50
            else curses.color_pair(1)
        )
        pl2_color = (
            curses.color_pair(2)
            if self.pl2 >= 115
            else curses.color_pair(3)
            if self.pl2 >= 65
            else curses.color_pair(1)
        )

        self.scr.addstr(y, cx, "│ PL1 (Sustained): ", curses.color_pair(1))
        self.draw_bar(y, cx + 18, 30, pl1_pct, pl1_color, f"{self.pl1}W")
        self.scr.addstr(" │", curses.color_pair(1))
        y += 1

        self.scr.addstr(y, cx, "│ PL2 (Turbo):     ", curses.color_pair(1))
        self.draw_bar(y, cx + 18, 30, pl2_pct, pl2_color, f"{self.pl2}W")
        self.scr.addstr(" │", curses.color_pair(1))
        y += 2

        self.scr.addstr(y, cx, "└" + "─" * 49 + "┘", curses.color_pair(7))
        return y + 1

    def draw_fan(self, h, w, start_y):
        cx = max(w // 2 - 24, 2)

        fan_icon = "🔥" if self.fan else "❄️"
        fan_text = "ACTIVE" if self.fan else "OFF"
        fan_color = curses.color_pair(2) if self.fan else curses.color_pair(3)

        self.scr.addstr(start_y, cx, "┌─ Fan Boost ─────┐", curses.color_pair(7))
        y = start_y + 1
        self.scr.addstr(y, cx, f"│ {fan_icon} Fan Boost: ", curses.color_pair(1))
        self.scr.addstr(fan_text, fan_color | curses.A_BOLD)
        self.scr.addstr(
            " " * (49 - len(fan_icon) - len(fan_text) - 4) + "│", curses.color_pair(1)
        )
        y += 2
        self.scr.addstr(y, cx, "└" + "─" * 49 + "┘", curses.color_pair(7))
        return y + 1

    def draw_profiles(self, h, w, start_y):
        cx = max(w // 2 - 28, 2)

        self.scr.addstr(
            start_y, cx, "┌─ Power Profiles ──────────────────┐", curses.color_pair(7)
        )
        y = start_y + 1

        for i, (key, profile) in enumerate(
            [
                ("1", "balanced"),
                ("2", "performance"),
                ("3", "turbo"),
            ]
        ):
            p = PROFILES[profile]
            is_active = self.current_profile == profile
            marker = "▶" if is_active else " "
            active_color = (
                curses.color_pair(p["color"]) | curses.A_BOLD
                if is_active
                else curses.color_pair(7)
            )
            self.scr.addstr(
                y,
                cx,
                f"│ [{key}] {marker} {p['desc']:<12} PL1={p['pl1']}W  PL2={p['pl2']}W",
                active_color,
            )
            extra = " ◀" if is_active else ""
            padding = (
                49
                - len(
                    f"[{key}] {marker} {p['desc']:<12} PL1={p['pl1']}W  PL2={p['pl2']}W"
                )
                - len(extra)
            )
            self.scr.addstr(
                " " * padding + extra + " │",
                active_color if is_active else curses.color_pair(7),
            )
            y += 1

        y += 1
        self.scr.addstr(y, cx, "└" + "─" * 49 + "┘", curses.color_pair(7))
        return y + 1

    def draw_footer(self, h, w, start_y):
        cx = max(w // 2 - 28, 2)

        svc_marker = "●" if self.svc else "○"
        svc_color = curses.color_pair(2) if self.svc else curses.color_pair(3)

        self.scr.addstr(
            start_y, cx, "┌─ Controls ─────────────────────────┐", curses.color_pair(7)
        )
        y = start_y + 1
        self.scr.addstr(
            y,
            cx,
            f"│ [F] Toggle Fan   [S] Auto-Start {svc_marker}",
            curses.color_pair(1),
        )
        self.scr.addstr(" " * 11 + "│", curses.color_pair(1))
        y += 1
        self.scr.addstr(
            y, cx, "│ [Q] Quit         Auto-refresh: ON  │", curses.color_pair(7)
        )
        y += 2
        self.scr.addstr(y, cx, "└" + "─" * 49 + "┘", curses.color_pair(7))
        return y + 1

    def draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()

        self.anim_frame += 1

        self.pl1 = read_rapl(0)
        self.pl2 = read_rapl(1)
        self.fan = read_fan()
        self.svc = service_active()
        self.current_profile = read_current_profile()

        start_y = self.draw_header(h, w)

        start_y = self.draw_status(h, w, start_y)
        start_y += 1
        start_y = self.draw_power(h, w, start_y)
        start_y += 1
        start_y = self.draw_fan(h, w, start_y)
        start_y += 1
        start_y = self.draw_profiles(h, w, start_y)
        start_y += 1
        start_y = self.draw_footer(h, w, start_y)

        if self.msg and time.time() - self.msg_time < 3:
            msg_color = curses.color_pair(2) | curses.A_BOLD
            self.scr.addstr(
                h - 2, max((w - len(self.msg)) // 2, 0), self.msg, msg_color
            )
        elif self.msg and time.time() - self.msg_time >= 3:
            self.msg = ""

        uptime = int(time.time() - self.start_time)
        mins, secs = uptime // 60, uptime % 60
        self.scr.addstr(h - 1, w - 12, f"{mins:02d}:{secs:02d}", curses.color_pair(7))

        self.scr.refresh()

    def handle(self, key):
        profiles_map = {
            ord("1"): "balanced",
            ord("2"): "performance",
            ord("3"): "turbo",
        }

        if key in profiles_map:
            p = profiles_map[key]
            self.msg = f"Applying {p.upper()}..."
            self.msg_time = time.time()

            def task():
                run(["profile", p])
                self.msg = f"Profile: {p.upper()}"
                self.msg_time = time.time()

            threading.Thread(target=task, daemon=True).start()

        elif key in (ord("f"), ord("F")):
            state = "0" if self.fan else "1"
            self.msg = f"Toggling fan {'ON' if state == '1' else 'OFF'}..."
            self.msg_time = time.time()

            def task():
                run(["fanboost", state])
                self.msg = f"Fan Boost: {'ON' if state == '1' else 'OFF'}"
                self.msg_time = time.time()

            threading.Thread(target=task, daemon=True).start()

        elif key in (ord("s"), ord("S")):
            if self.svc:
                cmd = ["service", "remove"]
                self.msg = "Removing service..."
            else:
                cmd = ["service", "balanced"]
                self.msg = "Installing service..."
            self.msg_time = time.time()

            def task():
                run(cmd)
                self.msg = "Service Updated"
                self.msg_time = time.time()

            threading.Thread(target=task, daemon=True).start()

        elif key in (ord("q"), ord("Q")):
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
