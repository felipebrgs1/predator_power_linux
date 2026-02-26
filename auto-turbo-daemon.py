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
        self.cpu_thermal_path = self._find_cpu_thermal_path()

        # Initialize desired profile if not exists
        if not os.path.exists(DESIRED_PROFILE_FILE):
            # Try to load from persistent storage
            # We need to find the real user home. Since we run as root, we look at the script path.
            # Script is in /home/USERNAME/repo/...
            parts = BASE_DIR.split("/")
            user_home = "/" + os.path.join(*parts[:3]) if len(parts) > 2 else "/root"
            
            persistent_file = os.path.join(
                user_home, ".config", "tdp-manager", "last_profile"
            )

            start_profile = "balanced"
            if os.path.exists(persistent_file):
                try:
                    with open(persistent_file, "r") as f:
                        start_profile = f.read().strip()
                    print(
                        f"Startup: Loaded persistent profile '{start_profile}' from {persistent_file}",
                        flush=True,
                    )
                except Exception as e:
                    print(f"Startup: Error loading persistent profile: {e}", flush=True)

            # If user left it on Turbo/Extreme, downgrade to Balanced for startup silence
            # The daemon will auto-engage Turbo if temps get high anyway.
            if start_profile in ["turbo", "extreme"]:
                print(
                    f"Startup: Downgrading '{start_profile}' to 'balanced' to prevent max fans at boot.",
                    flush=True,
                )
                start_profile = "balanced"

            self.set_desired_profile(start_profile)

    def _find_cpu_thermal_path(self):
        try:
            for i in range(10):
                path = f"/sys/class/thermal/thermal_zone{i}/temp"
                if os.path.exists(path):
                    type_path = f"/sys/class/thermal/thermal_zone{i}/type"
                    if os.path.exists(type_path):
                        with open(type_path, "r") as f:
                            ztype = f.read().strip()
                        if "x86_pkg" in ztype or "cpu" in ztype.lower():
                            return path
        except:
            pass
        return None

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

            # Ensure the user (non-root) can write to this file later
            # We assume the owner of the script is the user we want
            try:
                stat_info = os.stat(SCRIPT_PATH)
                os.chown(DESIRED_PROFILE_FILE, stat_info.st_uid, stat_info.st_gid)
            except:
                pass

        except Exception as e:
            print(f"Error setting profile file: {e}", flush=True)

    def get_cpu_temp(self):
        if not self.cpu_thermal_path:
            # Try to find it again if lost
            self.cpu_thermal_path = self._find_cpu_thermal_path()
            if not self.cpu_thermal_path:
                return None

        try:
            with open(self.cpu_thermal_path, "r") as f:
                return int(f.read().strip()) // 1000
        except:
            return None

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
        return None

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

    def get_current_gpu_limit(self):
        try:
            res = subprocess.run(
                ["nvidia-smi", "-q", "-d", "POWER"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if "Current Power Limit" in line:
                        # Format: "Current Power Limit                  : 80.00 W"
                        parts = line.split(":")
                        if len(parts) > 1:
                            val = parts[1].strip().split()[0]
                            return int(float(val))
        except:
            pass
        return None

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

            # Explicitly disable Fan Boost (Max Fans) on startup to ensure silence
            print("Startup: Forcing Fan Boost OFF...", flush=True)
            subprocess.run([SCRIPT_PATH, "fanboost", "0"], capture_output=True)

        except Exception as e:
            print(f"Startup reset error: {e}", flush=True)

        print("Startup: Waiting 15s for temperatures to settle...", flush=True)
        time.sleep(15)

        while self.running:
            try:
                cpu = self.get_cpu_temp()
                gpu = self.get_gpu_temp()

                # Treat None as 0 (safe fallback, don't trigger turbo on error)
                cpu_val = cpu if cpu is not None else 0
                gpu_val = gpu if gpu is not None else 0

                if cpu_val >= CPU_THRESHOLD or gpu_val >= GPU_THRESHOLD:
                    if not self.in_auto_turbo:
                        pl1, pl2 = self.get_current_limits()
                        gpu_limit = self.get_current_gpu_limit()
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

                        # 4. Restore GPU limit if we can read it
                        if gpu_limit:
                            print(f"Restoring GPU limit to {gpu_limit}W", flush=True)
                            subprocess.run(
                                [SCRIPT_PATH, "gpu", str(gpu_limit)],
                                capture_output=True,
                            )

                        self.in_auto_turbo = True
                elif cpu_val < CPU_HYSTERESIS and gpu_val < GPU_HYSTERESIS:
                    if self.in_auto_turbo:
                        print(
                            f"TEMP OK: CPU:{cpu_val}°C GPU:{gpu_val}°C. Restoring original profile settings.",
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
