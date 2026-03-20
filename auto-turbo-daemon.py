#!/usr/bin/env python3
"""Predator Power - Boot Profile Restorer
Runs at startup to restore saved profile and ensure silent fans."""

import subprocess
import os
import time

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tdp-manager.sh")
CONFIG = os.path.expanduser("~/.config/predator-power/last_profile")


def main():
    # Wait for kernel modules to initialize
    time.sleep(3)

    # Load saved profile or default to balanced
    profile = "balanced"
    if os.path.exists(CONFIG):
        try:
            saved = open(CONFIG).read().strip()
            if saved in ("balanced", "performance", "turbo"):
                profile = saved
        except:
            pass

    # Apply profile
    subprocess.run([SCRIPT, "profile", profile], capture_output=True, text=True)

    # Ensure fan boost is OFF (no noise at boot)
    subprocess.run([SCRIPT, "fanboost", "0"], capture_output=True, text=True)

    print(f"Boot: profile={profile}, fan=OFF")


if __name__ == "__main__":
    main()
