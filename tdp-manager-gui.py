#!/usr/bin/env python3
"""
TDP Manager GUI - Intel 12th Gen Power Control
A simple GTK3-based GUI for managing CPU power limits on Linux.
Similar to ThrottleStop for Windows.
"""

import gi
import subprocess
import os
import threading
import glob

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

# RAPL sysfs paths
RAPL_PATH = "/sys/class/powercap/intel-rapl/intel-rapl:0"

# Power profiles (PL1, PL2 in watts)
# Synced with tdp-manager.sh
# Format: "profile_id": ("Display Name", PL1, PL2, GPU_Limit)
PROFILES = {
    "silent": ("🔇 Silent", 15, 25, 80),
    "balanced": ("⚖️ Balanced", 50, 65, 80),
    "performance": ("⚡ Performance", 80, 115, 80),
    "turbo": ("🚀 Turbo", 100, 140, 80),
    "extreme": ("🔥 Extreme", 115, 160, 115),
}


class TDPManagerWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="TDP Manager")
        self.set_default_size(400, 600)
        self.set_resizable(False)
        self.active_profile = None
        self.lock_limits = False
        self.is_applying = False  # Safety lock for auth/subprocess

        # Apply dark theme
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", True)

        # Custom CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            window {
                background-color: #1a1a2e;
            }
            label {
                color: #eaeaea;
            }
            .title-label {
                font-size: 24px;
                font-weight: bold;
                color: #00d9ff;
            }
            .subtitle-label {
                font-size: 12px;
                color: #888888;
            }
            .value-label {
                font-size: 32px;
                font-weight: bold;
                color: #00ff88;
            }
            .unit-label {
                font-size: 14px;
                color: #888888;
            }
            .profile-button {
                padding: 12px 20px;
                font-size: 14px;
                border-radius: 8px;
                background: linear-gradient(135deg, #2d2d44 0%, #1a1a2e 100%);
                border: 1px solid #3d3d5c;
                color: #ffffff;
            }
            .profile-button:hover {
                background: linear-gradient(135deg, #3d3d5c 0%, #2d2d44 100%);
                border-color: #00d9ff;
            }
            .profile-button.active {
                background: linear-gradient(135deg, #00d9ff 0%, #0099cc 100%);
                color: #000000;
            }
            .apply-button {
                padding: 15px 30px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 10px;
                background: linear-gradient(135deg, #00d9ff 0%, #0099cc 100%);
                border: none;
                color: #000000;
            }
            .apply-button:hover {
                background: linear-gradient(135deg, #33e0ff 0%, #00b3e6 100%);
            }
            scale {
                min-height: 20px;
            }
            scale trough {
                background-color: #2d2d44;
                border-radius: 10px;
                min-height: 10px;
            }
            scale highlight {
                background: linear-gradient(90deg, #00ff88 0%, #00d9ff 100%);
                border-radius: 10px;
            }
            scale slider {
                background-color: #ffffff;
                border-radius: 50%;
                min-width: 20px;
                min-height: 20px;
            }
            .status-box {
                background-color: #2d2d44;
                border-radius: 10px;
                padding: 15px;
            }
            .temp-label {
                font-size: 18px;
                font-weight: bold;
            }
            .temp-ok { color: #00ff88; }
            .temp-warn { color: #ffaa00; }
            .temp-crit { color: #ff4444; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        self.add(main_box)

        # Header
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        title = Gtk.Label(label="TDP Manager")
        title.get_style_context().add_class("title-label")
        header_box.pack_start(title, False, False, 0)

        cpu_name = self.get_cpu_name()
        subtitle = Gtk.Label(label=cpu_name)
        subtitle.get_style_context().add_class("subtitle-label")
        header_box.pack_start(subtitle, False, False, 0)
        main_box.pack_start(header_box, False, False, 0)

        # Current Status Box
        status_frame = Gtk.Frame()
        status_frame.get_style_context().add_class("status-box")
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        status_box.set_halign(Gtk.Align.CENTER)
        status_box.set_margin_top(10)
        status_box.set_margin_bottom(10)
        status_box.set_margin_start(15)
        status_box.set_margin_end(15)

        # PL1 Display
        pl1_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pl1_label = Gtk.Label(label="PL1")
        pl1_label.get_style_context().add_class("subtitle-label")
        self.pl1_value = Gtk.Label(label="--")
        self.pl1_value.get_style_context().add_class("value-label")
        pl1_unit = Gtk.Label(label="watts")
        pl1_unit.get_style_context().add_class("unit-label")
        pl1_box.pack_start(pl1_label, False, False, 0)
        pl1_box.pack_start(self.pl1_value, False, False, 0)
        pl1_box.pack_start(pl1_unit, False, False, 0)
        status_box.pack_start(pl1_box, True, True, 0)

        # Temperature Display
        temp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        temp_label = Gtk.Label(label="CPU / GPU")
        temp_label.get_style_context().add_class("subtitle-label")
        self.temp_value = Gtk.Label(label="-- / --")
        self.temp_value.get_style_context().add_class("temp-label")
        temp_unit = Gtk.Label(label="°C")
        temp_unit.get_style_context().add_class("unit-label")
        temp_box.pack_start(temp_label, False, False, 0)
        temp_box.pack_start(self.temp_value, False, False, 0)
        temp_box.pack_start(temp_unit, False, False, 0)
        status_box.pack_start(temp_box, True, True, 0)

        # PL2 Display
        pl2_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pl2_label = Gtk.Label(label="PL2")
        pl2_label.get_style_context().add_class("subtitle-label")
        self.pl2_value = Gtk.Label(label="--")
        self.pl2_value.get_style_context().add_class("value-label")
        pl2_unit = Gtk.Label(label="watts")
        pl2_unit.get_style_context().add_class("unit-label")
        pl2_box.pack_start(pl2_label, False, False, 0)
        pl2_box.pack_start(self.pl2_value, False, False, 0)
        pl2_box.pack_start(pl2_unit, False, False, 0)
        status_box.pack_start(pl2_box, True, True, 0)

        status_frame.add(status_box)
        main_box.pack_start(status_frame, False, False, 0)

        # EC Status and Persistent Mode
        extra_info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        self.ec_label = Gtk.Label(label="Acer EC: --")
        self.ec_label.get_style_context().add_class("subtitle-label")
        extra_info_box.pack_start(self.ec_label, True, True, 0)

        self.keep_applied_switch = Gtk.Switch()
        self.keep_applied_switch.set_active(True)
        self.keep_applied_switch.set_tooltip_text(
            "Automatically re-apply limits if they drop (Anti-Throttle)"
        )
        keep_label = Gtk.Label(label="Keep Applied:")
        keep_label.get_style_context().add_class("subtitle-label")

        extra_info_box.pack_end(self.keep_applied_switch, False, False, 0)
        extra_info_box.pack_end(keep_label, False, False, 5)

        # Auto Turbo (Service Control)
        self.auto_turbo_switch = Gtk.Switch()
        self.auto_turbo_switch.set_active(self.is_service_active("auto-turbo"))
        self.auto_turbo_switch.set_tooltip_text(
            "Enable Background Auto Turbo Service (CPU 80°C / GPU 70°C)"
        )
        self.auto_turbo_switch.connect("notify::active", self.on_auto_turbo_toggled)
        auto_turbo_label = Gtk.Label(label="Background Auto Turbo:")
        auto_turbo_label.get_style_context().add_class("subtitle-label")

        extra_info_box.pack_end(self.auto_turbo_switch, False, False, 0)
        extra_info_box.pack_end(auto_turbo_label, False, False, 5)

        # Fan Boost Switch
        self.fan_boost_switch = Gtk.Switch()
        self.fan_boost_switch.connect("notify::active", self.on_fan_boost_toggled)
        self.fan_boost_switch.set_tooltip_text(
            "Force fans to maximum speed (Manual Turbo)"
        )
        fan_boost_label = Gtk.Label(label="Max Fan Force:")
        fan_boost_label.get_style_context().add_class("subtitle-label")

        extra_info_box.pack_start(fan_boost_label, False, False, 5)
        extra_info_box.pack_start(self.fan_boost_switch, False, False, 0)

        main_box.pack_start(extra_info_box, False, False, 0)

        # GPU Selection
        gpu_label = Gtk.Label(label="GPU TDP Limit (Optional Override)")
        gpu_label.set_halign(Gtk.Align.START)
        gpu_label.get_style_context().add_class("subtitle-label")
        main_box.pack_start(gpu_label, False, False, 5)

        gpu_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        gpu_box.set_halign(Gtk.Align.CENTER)

        self.gpu_80_btn = Gtk.Button(label="80W (Standard)")
        self.gpu_80_btn.get_style_context().add_class("profile-button")
        self.gpu_80_btn.connect("clicked", self.on_gpu_clicked, 80)

        self.gpu_115_btn = Gtk.Button(label="115W (Turbo)")
        self.gpu_115_btn.get_style_context().add_class("profile-button")
        self.gpu_115_btn.connect("clicked", self.on_gpu_clicked, 115)

        gpu_box.pack_start(self.gpu_80_btn, True, True, 0)
        gpu_box.pack_start(self.gpu_115_btn, True, True, 0)
        main_box.pack_start(gpu_box, False, False, 0)

        # Profile Buttons
        profiles_label = Gtk.Label(label="Power Profiles")
        profiles_label.set_halign(Gtk.Align.START)
        profiles_label.get_style_context().add_class("subtitle-label")
        main_box.pack_start(profiles_label, False, False, 5)

        profiles_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.profile_buttons = {}

        for profile_id, (profile_display, pl1, pl2, gpu) in PROFILES.items():
            btn = Gtk.Button(label=f"{profile_display} ({pl1}W/{pl2}W/{gpu}W)")
            btn.get_style_context().add_class("profile-button")
            btn.connect("clicked", self.on_profile_clicked, profile_id)
            profiles_box.pack_start(btn, False, False, 0)
            self.profile_buttons[profile_id] = btn

        main_box.pack_start(profiles_box, False, False, 0)

        # Custom Power Section
        custom_label = Gtk.Label(label="Custom Power Limits")
        custom_label.set_halign(Gtk.Align.START)
        custom_label.get_style_context().add_class("subtitle-label")
        main_box.pack_start(custom_label, False, False, 10)

        # PL1 Slider
        pl1_slider_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        pl1_slider_label = Gtk.Label(label="PL1:")
        pl1_slider_label.set_width_chars(4)
        self.pl1_slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 10, 150, 5
        )
        self.pl1_slider.set_value(60)
        self.pl1_slider.set_hexpand(True)
        self.pl1_slider_value = Gtk.Label(label="60W")
        self.pl1_slider_value.set_width_chars(5)
        self.pl1_slider.connect("value-changed", self.on_pl1_changed)
        pl1_slider_box.pack_start(pl1_slider_label, False, False, 0)
        pl1_slider_box.pack_start(self.pl1_slider, True, True, 0)
        pl1_slider_box.pack_start(self.pl1_slider_value, False, False, 0)
        main_box.pack_start(pl1_slider_box, False, False, 0)

        # PL2 Slider
        pl2_slider_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        pl2_slider_label = Gtk.Label(label="PL2:")
        pl2_slider_label.set_width_chars(4)
        self.pl2_slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 15, 180, 5
        )
        self.pl2_slider.set_value(80)
        self.pl2_slider.set_hexpand(True)
        self.pl2_slider_value = Gtk.Label(label="80W")
        self.pl2_slider_value.set_width_chars(5)
        self.pl2_slider.connect("value-changed", self.on_pl2_changed)
        pl2_slider_box.pack_start(pl2_slider_label, False, False, 0)
        pl2_slider_box.pack_start(self.pl2_slider, True, True, 0)
        pl2_slider_box.pack_start(self.pl2_slider_value, False, False, 0)
        main_box.pack_start(pl2_slider_box, False, False, 0)

        # Apply Button
        apply_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        apply_box.set_halign(Gtk.Align.CENTER)

        self.apply_btn = Gtk.Button(label="⚡ Apply Custom Settings")
        self.apply_btn.get_style_context().add_class("apply-button")
        self.apply_btn.connect("clicked", self.on_apply_clicked)
        apply_box.pack_start(self.apply_btn, False, False, 0)
        main_box.pack_start(apply_box, False, False, 10)

        # Status bar
        self.status_label = Gtk.Label(label="Ready")
        self.status_label.get_style_context().add_class("subtitle-label")
        main_box.pack_end(self.status_label, False, False, 0)

        # Start update timer
        self.update_status()
        GLib.timeout_add(1000, self.update_status)

    def get_cpu_name(self):
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":")[1].strip()
        except Exception:
            pass
        return "Intel CPU"

    def read_rapl_value(self, constraint):
        try:
            with open(f"{RAPL_PATH}/constraint_{constraint}_power_limit_uw", "r") as f:
                return int(f.read().strip()) // 1000000
        except Exception:
            return 0

    def is_service_active(self, service_name):
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
            )
            return result.stdout.strip() == "active"
        except Exception:
            return False

    def get_auth_command(self):
        """Returns ['pkexec'] if not root, else empty list"""
        if os.getuid() == 0:
            return []
        return ["pkexec"]

    def on_auto_turbo_toggled(self, switch, gparam):
        if self.is_applying:
            return

        active = switch.get_active()
        action = "start" if active else "stop"
        self.is_applying = True
        self.status_label.set_text(
            f"{'Starting' if active else 'Stopping'} background service..."
        )

        def run_action():
            try:
                if active:
                    # Generate a dynamic service file for the current location/user
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    service_content = f"""[Unit]
Description=Predator Auto Turbo Fan Daemon
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {os.path.join(script_dir, "auto-turbo-daemon.py")}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
                    tmp_service = "/tmp/auto-turbo.service"
                    with open(tmp_service, "w") as f:
                        f.write(service_content)

                    # Install the dynamic service
                    auth = self.get_auth_command()
                    subprocess.run(
                        auth
                        + [
                            "cp",
                            tmp_service,
                            "/etc/systemd/system/auto-turbo.service",
                        ],
                        capture_output=True,
                    )
                    subprocess.run(
                        auth + ["systemctl", "daemon-reload"], capture_output=True
                    )

                subprocess.run(
                    auth + ["systemctl", action, "auto-turbo"], capture_output=True
                )
                # Also enable/disable for boot persistence
                boot_action = "enable" if active else "disable"
                subprocess.run(
                    auth + ["systemctl", boot_action, "auto-turbo"],
                    capture_output=True,
                )

                GLib.idle_add(
                    self.status_label.set_text,
                    f"✓ Auto Turbo Service {'Enabled' if active else 'Disabled'}",
                )
            except Exception as e:
                GLib.idle_add(self.status_label.set_text, f"✗ Error: {str(e)}")
            finally:

                def unlock():
                    self.is_applying = False

                GLib.idle_add(unlock)

        thread = threading.Thread(target=run_action)
        thread.daemon = True
        thread.start()

    def on_fan_boost_toggled(self, switch, gparam):
        if self.is_applying:
            return

        if not hasattr(self, "_updating_from_hw") or not self._updating_from_hw:
            active = switch.get_active()
            state = "1" if active else "0"
            self.is_applying = True
            self.status_label.set_text(
                f"{'Enabling' if active else 'Disabling'} Fan Boost..."
            )

            def run_action():
                # For now let's use a trick
                auth = self.get_auth_command()
                subprocess.run(
                    auth
                    + [
                        "bash",
                        "-c",
                        f"echo {state} > /sys/devices/platform/acer-thermal-lite/fan_boost",
                    ],
                    capture_output=True,
                )
                GLib.idle_add(
                    self.status_label.set_text,
                    f"✓ Fan Boost {'Enabled' if active else 'Disabled'}",
                )

                def unlock():
                    self.is_applying = False

                GLib.idle_add(unlock)

            thread = threading.Thread(target=run_action)
            thread.daemon = True
            thread.start()

    def on_gpu_clicked(self, button, limit):
        if self.is_applying:
            return

        self.is_applying = True
        self.status_label.set_text(f"Setting GPU limit to {limit}W...")

        def run_action():
            script_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "tdp-manager.sh"
            )
            auth = self.get_auth_command()
            subprocess.run(auth + [script_path, "gpu", str(limit)], capture_output=True)
            GLib.idle_add(self.status_label.set_text, f"✓ GPU Limit set to {limit}W")

            def unlock():
                self.is_applying = False

            GLib.idle_add(unlock)

        thread = threading.Thread(target=run_action)
        thread.daemon = True
        thread.start()

    def read_gpu_temperature(self):
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except Exception:
            pass
        return 0

    def read_gpu_limit(self):
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "-q",
                    "-d",
                    "POWER",
                ],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "Current Power Limit" in line:
                        return int(float(line.split(":")[1].strip().split()[0]))
        except Exception:
            pass
        return 0

    def read_fan_boost(self):
        try:
            path = "/sys/devices/platform/acer-thermal-lite/fan_boost"
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read().strip() == "1"
        except Exception:
            pass
        return False

    def read_temperature(self):
        try:
            # Try different thermal zone paths
            for i in range(10):
                path = f"/sys/class/thermal/thermal_zone{i}/temp"
                if os.path.exists(path):
                    try:
                        type_path = f"/sys/class/thermal/thermal_zone{i}/type"
                        with open(type_path, "r") as f:
                            zone_type = f.read().strip()
                        # Prefer CPU zones
                        if "x86_pkg" in zone_type or "cpu" in zone_type.lower():
                            with open(path, "r") as f:
                                return int(f.read().strip()) // 1000
                    except Exception:
                        continue
            # Fallback to zone 0
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return int(f.read().strip()) // 1000
        except Exception:
            return 0

    def update_status(self):
        if self.is_applying:
            return True  # Don't update or trigger actions if busy

        pl1 = self.read_rapl_value(0)
        pl2 = self.read_rapl_value(1)
        temp = self.read_temperature()
        fan_boost = self.read_fan_boost()

        self._updating_from_hw = True
        self.fan_boost_switch.set_active(fan_boost)
        self._updating_from_hw = False

        # Read EC status
        ec_status = "unavailable"
        try:
            paths = glob.glob("/sys/class/platform-profile/*/profile")
            if paths:
                with open(paths[0], "r") as f:
                    ec_status = f.read().strip()
        except Exception:
            pass

        self.ec_label.set_text(f"Acer EC: {ec_status}")
        if ec_status == "unavailable":
            self.ec_label.set_markup(
                "<span color='#ffaa00'>Acer EC: unavailable (thermal module missing)</span>"
            )

        self.pl1_value.set_text(str(pl1))

        self.pl2_value.set_text(str(pl2))

        gpu_temp = self.read_gpu_temperature()
        gpu_limit = self.read_gpu_limit()
        self.temp_value.set_text(f"{temp} / {gpu_temp}")
        max_temp = max(temp, gpu_temp)

        # Update temperature color
        ctx = self.temp_value.get_style_context()
        ctx.remove_class("temp-ok")
        ctx.remove_class("temp-warn")
        ctx.remove_class("temp-crit")

        if max_temp < 70:
            ctx.add_class("temp-ok")
        elif max_temp < 85:
            ctx.add_class("temp-warn")
        else:
            ctx.add_class("temp-crit")

        # Update sliders to match current values
        if not self.pl1_slider.has_focus():
            self.pl1_slider.set_value(pl1)
        if not self.pl2_slider.has_focus():
            self.pl2_slider.set_value(pl2)

        # Highlight active profile
        self.active_profile = None
        for profile_id, btn in self.profile_buttons.items():
            if profile_id in PROFILES:
                _, profile_pl1, profile_pl2, profile_gpu = PROFILES[profile_id]
                ctx = btn.get_style_context()

                # GPU limit fluctuates due to Dynamic Boost (e.g. 80W base can show as 95W)
                # We use a larger tolerance (20W) to keep the profile highlighted
                gpu_match = abs(gpu_limit - profile_gpu) <= 20

                if pl1 == profile_pl1 and pl2 == profile_pl2 and gpu_match:
                    ctx.add_class("active")
                    self.active_profile = profile_id
                else:
                    ctx.remove_class("active")

        # Update GPU selection buttons highlighting
        ctx_80 = self.gpu_80_btn.get_style_context()
        ctx_115 = self.gpu_115_btn.get_style_context()
        ctx_80.remove_class("active")
        ctx_115.remove_class("active")

        # Range-based highlighting for GPU targets
        if gpu_limit <= 100:  # 80W base + Dynamic Boost
            ctx_80.add_class("active")
        elif gpu_limit >= 110:  # 115W base
            ctx_115.add_class("active")

        # Persistent Mode Logic (Anti-Throttle)
        if self.keep_applied_switch.get_active() and self.active_profile:
            _, target_pl1, target_pl2, target_gpu = PROFILES[self.active_profile]
            # Precise check for CPU, tolerant check for GPU
            gpu_diff = abs(gpu_limit - target_gpu) > 10
            if pl1 != target_pl1 or pl2 != target_pl2 or gpu_diff:
                # Re-apply only if significant drop or CPU change
                # We use apply_power_limits to avoid double platform-profile hit
                if pl1 != target_pl1 or pl2 != target_pl2:
                    self.apply_power_limits(target_pl1, target_pl2)

        return True  # Continue timer

    def on_pl1_changed(self, slider):
        value = int(slider.get_value())
        self.pl1_slider_value.set_text(f"{value}W")

    def on_pl2_changed(self, slider):
        value = int(slider.get_value())
        self.pl2_slider_value.set_text(f"{value}W")

    def on_profile_clicked(self, button, profile_id):
        self.apply_named_profile(profile_id)

    def on_apply_clicked(self, button):
        pl1 = int(self.pl1_slider.get_value())
        pl2 = int(self.pl2_slider.get_value())
        self.apply_power_limits(pl1, pl2)

    def apply_named_profile(self, profile_id):
        if self.is_applying:
            return
        self.is_applying = True
        self.status_label.set_text(f"Applying profile: {profile_id}...")

        # Save desired profile for the background daemon and persistence
        try:
            # Update running daemon
            try:
                with open("/tmp/tdp_desired_profile", "w") as f:
                    f.write(profile_id)
            except Exception:
                pass

            # Save persistence for next boot
            config_dir = os.path.expanduser("~/.config/tdp-manager")
            if not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)

            with open(os.path.join(config_dir, "last_profile"), "w") as f:
                f.write(profile_id)
        except Exception as e:
            print(f"Warning: Could not save profile persistence: {e}")

        def apply():
            script_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "tdp-manager.sh"
            )

            try:
                auth = self.get_auth_command()
                result = subprocess.run(
                    auth + [script_path, "profile", profile_id],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    GLib.idle_add(
                        self.status_label.set_text, f"✓ Applied Profile: {profile_id}"
                    )
                else:
                    error_msg = (
                        result.stderr.strip()
                        if result.stderr
                        else "Auth cancelled or error"
                    )
                    GLib.idle_add(self.status_label.set_text, f"✗ Failed: {error_msg}")
            except Exception as e:
                GLib.idle_add(self.status_label.set_text, f"✗ Error: {str(e)}")
            finally:

                def unlock():
                    self.is_applying = False

                GLib.idle_add(unlock)

        thread = threading.Thread(target=apply)
        thread.daemon = True
        thread.start()

    def apply_power_limits(self, pl1, pl2):
        if self.is_applying:
            return
        self.is_applying = True
        self.status_label.set_text("Applying custom limits...")

        def apply():
            script_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "tdp-manager.sh"
            )

            try:
                auth = self.get_auth_command()
                result = subprocess.run(
                    auth + [script_path, "set", str(pl1), str(pl2)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    GLib.idle_add(
                        self.status_label.set_text,
                        f"✓ Applied Limits: PL1={pl1}W PL2={pl2}W",
                    )
                else:
                    error_msg = (
                        result.stderr.strip()
                        if result.stderr
                        else "Auth cancelled or error"
                    )
                    GLib.idle_add(self.status_label.set_text, f"✗ Failed: {error_msg}")
            except Exception as e:
                GLib.idle_add(self.status_label.set_text, f"✗ Error: {str(e)}")
            finally:

                def unlock():
                    self.is_applying = False

                GLib.idle_add(unlock)

        thread = threading.Thread(target=apply)
        thread.daemon = True
        thread.start()


def main():
    win = TDPManagerWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
