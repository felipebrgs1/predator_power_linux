#!/usr/bin/env python3
"""
TDP Manager GUI - Intel 12th Gen Power Control
A simple GTK3-based GUI for managing CPU power limits on Linux.
Similar to ThrottleStop for Windows.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk
import subprocess
import os
import threading

# RAPL sysfs paths
RAPL_PATH = "/sys/class/powercap/intel-rapl/intel-rapl:0"

# Power profiles (PL1, PL2 in watts)
PROFILES = {
    "🔇 Silent": (15, 25),
    "⚖️ Balanced": (35, 45),
    "⚡ Performance": (60, 80),
    "🚀 Turbo": (80, 115),
    "🔥 Extreme": (115, 150),
}

class TDPManagerWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="TDP Manager")
        self.set_default_size(400, 500)
        self.set_resizable(False)
        
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
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
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
        temp_label = Gtk.Label(label="TEMP")
        temp_label.get_style_context().add_class("subtitle-label")
        self.temp_value = Gtk.Label(label="--")
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
        
        # Profile Buttons
        profiles_label = Gtk.Label(label="Power Profiles")
        profiles_label.set_halign(Gtk.Align.START)
        profiles_label.get_style_context().add_class("subtitle-label")
        main_box.pack_start(profiles_label, False, False, 5)
        
        profiles_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.profile_buttons = {}
        
        for profile_name, (pl1, pl2) in PROFILES.items():
            btn = Gtk.Button(label=f"{profile_name} ({pl1}W / {pl2}W)")
            btn.get_style_context().add_class("profile-button")
            btn.connect("clicked", self.on_profile_clicked, profile_name)
            profiles_box.pack_start(btn, False, False, 0)
            self.profile_buttons[profile_name] = btn
        
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
        self.pl1_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 150, 5)
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
        self.pl2_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 15, 180, 5)
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
        except:
            pass
        return "Intel CPU"
    
    def read_rapl_value(self, constraint):
        try:
            with open(f"{RAPL_PATH}/constraint_{constraint}_power_limit_uw", "r") as f:
                return int(f.read().strip()) // 1000000
        except:
            return 0
    
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
                    except:
                        continue
            # Fallback to zone 0
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return int(f.read().strip()) // 1000
        except:
            return 0
    
    def update_status(self):
        pl1 = self.read_rapl_value(0)
        pl2 = self.read_rapl_value(1)
        temp = self.read_temperature()
        
        self.pl1_value.set_text(str(pl1))
        self.pl2_value.set_text(str(pl2))
        self.temp_value.set_text(str(temp))
        
        # Update temperature color
        ctx = self.temp_value.get_style_context()
        ctx.remove_class("temp-ok")
        ctx.remove_class("temp-warn")
        ctx.remove_class("temp-crit")
        
        if temp < 70:
            ctx.add_class("temp-ok")
        elif temp < 85:
            ctx.add_class("temp-warn")
        else:
            ctx.add_class("temp-crit")
        
        # Update sliders to match current values
        if not self.pl1_slider.has_focus():
            self.pl1_slider.set_value(pl1)
        if not self.pl2_slider.has_focus():
            self.pl2_slider.set_value(pl2)
        
        # Highlight active profile
        for name, btn in self.profile_buttons.items():
            profile_pl1, profile_pl2 = PROFILES[name]
            ctx = btn.get_style_context()
            if pl1 == profile_pl1 and pl2 == profile_pl2:
                ctx.add_class("active")
            else:
                ctx.remove_class("active")
        
        return True  # Continue timer
    
    def on_pl1_changed(self, slider):
        value = int(slider.get_value())
        self.pl1_slider_value.set_text(f"{value}W")
    
    def on_pl2_changed(self, slider):
        value = int(slider.get_value())
        self.pl2_slider_value.set_text(f"{value}W")
    
    def on_profile_clicked(self, button, profile_name):
        pl1, pl2 = PROFILES[profile_name]
        self.apply_power_limits(pl1, pl2)
    
    def on_apply_clicked(self, button):
        pl1 = int(self.pl1_slider.get_value())
        pl2 = int(self.pl2_slider.get_value())
        self.apply_power_limits(pl1, pl2)
    
    def apply_power_limits(self, pl1, pl2):
        self.status_label.set_text("Applying...")
        
        def apply():
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tdp-manager.sh")
            
            try:
                result = subprocess.run(
                    ["pkexec", script_path, "set", str(pl1), str(pl2)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    GLib.idle_add(self.status_label.set_text, f"✓ Applied: PL1={pl1}W PL2={pl2}W")
                else:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                    GLib.idle_add(self.status_label.set_text, f"✗ Failed: {error_msg}")
            except subprocess.TimeoutExpired:
                GLib.idle_add(self.status_label.set_text, "✗ Timeout - operation cancelled")
            except Exception as e:
                GLib.idle_add(self.status_label.set_text, f"✗ Error: {str(e)}")
        
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
