#!/usr/bin/env python3
import subprocess
import os
import time
import signal
import sys

# Configuration
CPU_THRESHOLD = 80
GPU_THRESHOLD = 70
CPU_HYSTERESIS = 75
GPU_HYSTERESIS = 65
CHECK_INTERVAL = 2  # Seconds

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(BASE_DIR, "tdp-manager.sh")
DESIRED_PROFILE_FILE = "/tmp/tdp_desired_profile"


class AutoTurboDaemon:
    def __init__(self):
        self.in_auto_turbo = False
        self.running = True

        # Initialize desired profile if not exists
        if not os.path.exists(DESIRED_PROFILE_FILE):
            self.set_desired_profile("balanced")

    def get_desired_profile(self):
        try:
            with open(DESIRED_PROFILE_FILE, "r") as f:
                return f.read().strip()
        except:
            return "balanced"

    def set_desired_profile(self, profile):
        try:
            with open(DESIRED_PROFILE_FILE, "w") as f:
                f.write(profile)
        except:
            pass

    def get_cpu_temp(self):
        try:
            for i in range(10):
                path = f"/sys/class/thermal/thermal_zone{i}/temp"
                if os.path.exists(path):
                    with open(f"/sys/class/thermal/thermal_zone{i}/type", "r") as f:
                        ztype = f.read().strip()
                    if "x86_pkg" in ztype or "cpu" in ztype.lower():
                        with open(path, "r") as f:
                            return int(f.read().strip()) // 1000
        except:
            pass
        return 0

    def get_gpu_temp(self):
        try:
            res = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode == 0:
                return int(res.stdout.strip())
        except:
            pass
        return 0

    def apply_profile(self, profile):
        # When running as service (root), call script directly
        subprocess.run([SCRIPT_PATH, "profile", profile], capture_output=True)

    def run(self):
        print(f"Auto Turbo Daemon started. (C{CPU_THRESHOLD}/G{GPU_THRESHOLD})")
        while self.running:
            cpu = self.get_cpu_temp()
            gpu = self.get_gpu_temp()

            desired = self.get_desired_profile()

            if cpu >= CPU_THRESHOLD or gpu >= GPU_THRESHOLD:
                if not self.in_auto_turbo:
                    print(f"TEMP HIGH: CPU:{cpu}°C GPU:{gpu}°C. Activating TURBO Fans.")
                    self.apply_profile("turbo")
                    self.in_auto_turbo = True
            elif cpu < CPU_HYSTERESIS and gpu < GPU_HYSTERESIS:
                if self.in_auto_turbo:
                    print(f"TEMP OK: CPU:{cpu}°C GPU:{gpu}°C. Restoring {desired}.")
                    self.apply_profile(desired)
                    self.in_auto_turbo = False

            time.sleep(CHECK_INTERVAL)


def signal_handler(sig, frame):
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    daemon = AutoTurboDaemon()
    daemon.run()
