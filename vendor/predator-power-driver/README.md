# Predator Power Driver

Kernel module used by Predator Power Manager for Acer Predator gaming WMI controls.

It intentionally exposes only power-related controls:

- `/sys/devices/platform/predator-power/thermal_profile`
- `/sys/devices/platform/predator-power/turbo_oc`
- `/sys/devices/platform/predator-power/fan_boost`

Keyboard RGB and hotkey input handling are intentionally not included.
