# Predator Power Driver

Kernel module used by Predator Power Manager for Acer Predator gaming WMI controls.

It intentionally exposes only power-related controls:

- `/sys/devices/platform/predator-power/thermal_profile`
- `/sys/devices/platform/predator-power/turbo_oc`
- `/sys/devices/platform/predator-power/fan_boost`
- `/sys/devices/platform/predator-power/fan_mode`
- `/sys/devices/platform/predator-power/cpu_fan_rpm`
- `/sys/devices/platform/predator-power/gpu_fan_rpm`

Keyboard RGB and hotkey input handling are intentionally not included.

`fan_mode` supports `1` for automatic and `2` for turbo. Mode `3` is intentionally rejected because it stopped the fans on tested hardware.
