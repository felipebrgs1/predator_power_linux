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


def safe_addstr(win, y, x, text, attr=None):
    try:
        if attr:
            win.addstr(y, x, text, attr)
        else:
            win.addstr(y, x, text)
    except curses.error:
        pass


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
        curses.curs_set(0)
        scr.nodelay(True)
        scr.timeout(100)

    def draw_bar(self, y, x, width, filled, color_pair, label=""):
        bar_width = width - len(label) - 2
        if bar_width <= 0:
            bar_width = 10
        fill_width = int(bar_width * filled)
        bar = "|" * fill_width + "." * (bar_width - fill_width)
        safe_addstr(self.scr, y, x, "[%s] %s" % (bar, label), color_pair)

    def draw_header(self, h, w):
        cy = 1
        title = " PREDATOR POWER MANAGER "
        safe_addstr(
            self.scr,
            cy,
            (w - len(title)) // 2,
            title,
            curses.color_pair(5) | curses.A_BOLD,
        )

        cy += 1
        line = "=" * (w - 4)
        safe_addstr(self.scr, cy, 2, line, curses.color_pair(7))

        return cy + 1

    def draw_status(self, h, w, start_y):
        cx = max(w // 2 - 24, 2)

        safe_addstr(
            self.scr, start_y, cx, "+- System Status ------+", curses.color_pair(7)
        )
        y = start_y + 1

        cpu_short = self.cpu_name[:38] if len(self.cpu_name) > 38 else self.cpu_name
        safe_addstr(self.scr, y, cx, "| CPU: %-36s |" % cpu_short, curses.color_pair(1))
        y += 1
        profile_color = PROFILES.get(self.current_profile, {}).get("color", 1)
        safe_addstr(
            self.scr,
            y,
            cx,
            "| Profile: %-28s |" % self.current_profile,
            curses.color_pair(profile_color) | curses.A_BOLD,
        )
        y += 2
        safe_addstr(self.scr, y, cx, "+" + "-" * 25 + "+", curses.color_pair(7))
        return y + 1

    def draw_power(self, h, w, start_y):
        cx = max(w // 2 - 24, 2)

        safe_addstr(
            self.scr, start_y, cx, "+- Power Limits --------+", curses.color_pair(7)
        )
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

        safe_addstr(self.scr, y, cx, "| PL1 (Sustained):", curses.color_pair(1))
        self.draw_bar(y, cx + 18, 28, pl1_pct, pl1_color, "%dW" % self.pl1)
        safe_addstr(self.scr, y, cx + 48, "|", curses.color_pair(1))
        y += 1

        safe_addstr(self.scr, y, cx, "| PL2 (Turbo):    ", curses.color_pair(1))
        self.draw_bar(y, cx + 18, 28, pl2_pct, pl2_color, "%dW" % self.pl2)
        safe_addstr(self.scr, y, cx + 48, "|", curses.color_pair(1))
        y += 2
        safe_addstr(self.scr, y, cx, "+" + "-" * 25 + "+", curses.color_pair(7))
        return y + 1

    def draw_fan(self, h, w, start_y):
        cx = max(w // 2 - 24, 2)

        fan_icon = "*" if self.fan else "-"
        fan_text = "ACTIVE" if self.fan else "OFF"
        fan_color = curses.color_pair(2) if self.fan else curses.color_pair(3)

        safe_addstr(
            self.scr, start_y, cx, "+- Fan Boost -------------+", curses.color_pair(7)
        )
        y = start_y + 1
        safe_addstr(
            self.scr, y, cx, "| [%s] Fan Boost: " % fan_icon, curses.color_pair(1)
        )
        safe_addstr(self.scr, y, cx + 17, fan_text, fan_color | curses.A_BOLD)
        safe_addstr(self.scr, y, cx + 24, " " * 24 + "|", curses.color_pair(1))
        y += 2
        safe_addstr(self.scr, y, cx, "+" + "-" * 25 + "+", curses.color_pair(7))
        return y + 1

    def draw_profiles(self, h, w, start_y):
        cx = max(w // 2 - 28, 2)

        safe_addstr(
            self.scr,
            start_y,
            cx,
            "+- Power Profiles -------------------+",
            curses.color_pair(7),
        )
        y = start_y + 1

        for i, (key, profile) in enumerate(
            [("1", "balanced"), ("2", "performance"), ("3", "turbo")]
        ):
            p = PROFILES[profile]
            is_active = self.current_profile == profile
            marker = ">" if is_active else " "
            active_color = (
                curses.color_pair(p["color"]) | curses.A_BOLD
                if is_active
                else curses.color_pair(7)
            )
            line = "| [%s] %s %-11s  PL1=%2dW  PL2=%3dW" % (
                key,
                marker,
                p["desc"],
                p["pl1"],
                p["pl2"],
            )
            if is_active:
                line += " <"
            safe_addstr(self.scr, y, cx, line, active_color)
            safe_addstr(
                self.scr,
                y,
                cx + 46,
                " " * 17 + "|",
                curses.color_pair(7) if not is_active else active_color,
            )
            y += 1

        y += 1
        safe_addstr(self.scr, y, cx, "+" + "-" * 46 + "+", curses.color_pair(7))
        return y + 1

    def draw_footer(self, h, w, start_y):
        cx = max(w // 2 - 28, 2)

        svc_marker = "*" if self.svc else "o"

        safe_addstr(
            self.scr,
            start_y,
            cx,
            "+- Controls ---------------------------+",
            curses.color_pair(7),
        )
        y = start_y + 1
        safe_addstr(
            self.scr,
            y,
            cx,
            "| [F] Toggle Fan    [S] Auto-Start (%s)   |" % svc_marker,
            curses.color_pair(1),
        )
        y += 1
        safe_addstr(
            self.scr,
            y,
            cx,
            "| [Q] Quit          Auto-refresh: ON       |",
            curses.color_pair(7),
        )
        y += 2
        safe_addstr(self.scr, y, cx, "+" + "-" * 46 + "+", curses.color_pair(7))
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
            safe_addstr(
                self.scr, h - 2, max((w - len(self.msg)) // 2, 0), self.msg, msg_color
            )
        elif self.msg and time.time() - self.msg_time >= 3:
            self.msg = ""

        uptime = int(time.time() - self.start_time)
        mins, secs = uptime // 60, uptime % 60
        safe_addstr(
            self.scr, h - 1, w - 7, "%02d:%02d" % (mins, secs), curses.color_pair(7)
        )

        self.scr.refresh()

    def handle(self, key):
        profiles_map = {
            ord("1"): "balanced",
            ord("2"): "performance",
            ord("3"): "turbo",
        }

        if key in profiles_map:
            p = profiles_map[key]
            self.msg = "Applying %s..." % p.upper()
            self.msg_time = time.time()

            def task():
                run(["profile", p])
                self.msg = "Profile: %s" % p.upper()
                self.msg_time = time.time()

            threading.Thread(target=task, daemon=True).start()

        elif key in (ord("f"), ord("F")):
            state = "0" if self.fan else "1"
            self.msg = "Toggling fan %s..." % ("ON" if state == "1" else "OFF")
            self.msg_time = time.time()

            def task():
                run(["fanboost", state])
                self.msg = "Fan Boost: %s" % ("ON" if state == "1" else "OFF")
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
