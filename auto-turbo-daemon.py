#!/usr/bin/env python3
import subprocess
import os
import time
import signal
import sys

# Configuration
CPU_THRESHOLD = 85
GPU_THRESHOLD = 75
CPU_HYSTERESIS = 80
GPU_HYSTERESIS = 70
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

    def get_current_limits(self):
        try:
            with open(
                "/sys/class/powercap/intel-rapl/intel-rapl:0/constraint_0_power_limit_uw",
                "r",
            ) as f:
                pl1 = int(f.read().strip()) // 1000000
            with open(
                "/sys/class/powercap/intel-rapl/intel-rapl:0/constraint_1_power_limit_uw",
                "r",
            ) as f:
                pl2 = int(f.read().strip()) // 1000000
            return pl1, pl2
        except:
            return 80, 115

    def run(self):
        print(
            f"Auto Turbo Daemon started. (CPU >= {CPU_THRESHOLD}°C or GPU >= {GPU_THRESHOLD}°C)",
            flush=True,
        )

        # Ensure we start in a clean state (restore desired profile on startup)
        # This prevents "sticky" Turbo from previous sessions
        try:
            desired = self.get_desired_profile()
            print(f"Startup: Ensuring current profile is '{desired}'", flush=True)
            subprocess.run([SCRIPT_PATH, "profile", desired], capture_output=True)
        except Exception as e:
            print(f"Startup reset error: {e}", flush=True)

        print("Startup: Waiting 15s for temperatures to settle...", flush=True)
        time.sleep(15)

        while self.running:
            try:
                cpu = self.get_cpu_temp()
                gpu = self.get_gpu_temp()

                if cpu >= CPU_THRESHOLD or gpu >= GPU_THRESHOLD:
                    if not self.in_auto_turbo:
                        pl1, pl2 = self.get_current_limits()
                        print(
                            f"TEMP HIGH: CPU:{cpu}°C GPU:{gpu}°C. Activating MAX Fans (Performance mode)...",
                            flush=True,
                        )
                        # 1. Force EC into Turbo (Performance) mode - This will ramp up fans
                        subprocess.run(
                            [SCRIPT_PATH, "platform", "performance"],
                            capture_output=True,
                        )
                        # 2. Wait a bit for EC to stabilize
                        time.sleep(0.5)
                        # 3. Restore the user power limits immediately (hardware override bypass)
                        print(
                            f"Restoring power limits to PL1={pl1}W PL2={pl2}W",
                            flush=True,
                        )
                        subprocess.run(
                            [SCRIPT_PATH, "set", str(pl1), str(pl2)],
                            capture_output=True,
                        )

                        self.in_auto_turbo = True
                elif cpu < CPU_HYSTERESIS and gpu < GPU_HYSTERESIS:
                    if self.in_auto_turbo:
                        print(
                            f"TEMP OK: CPU:{cpu}°C GPU:{gpu}°C. Restoring original profile settings.",
                            flush=True,
                        )
                        desired = self.get_desired_profile()
                        subprocess.run(
                            [SCRIPT_PATH, "profile", desired], capture_output=True
                        )
                        self.in_auto_turbo = False
            except Exception as e:
                print(f"Error in daemon loop: {e}", flush=True)

            time.sleep(CHECK_INTERVAL)


def signal_handler(sig, frame):
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    daemon = AutoTurboDaemon()
    daemon.run()
