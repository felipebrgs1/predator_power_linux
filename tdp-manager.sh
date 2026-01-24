#!/bin/bash
# TDP Manager for Intel 12th Gen (Alder Lake) - Acer Predator PT316-51s
# Author: Felipe B.
# Controls CPU power limits via intel_rapl sysfs interface

# Configuration
CONFIG_FILE="${HOME}/.config/tdp-manager/config"
RAPL_PATH="/sys/class/powercap/intel-rapl/intel-rapl:0"
LOG_FILE="/tmp/tdp-manager.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Power profiles (values in watts)
# Format: "PL1 PL2 governor EPP platform_profile"
# platform_profile: low-power, quiet, balanced (Acer EC modes)
declare -A PROFILES=(
    ["silent"]="15 25 powersave power quiet"                    # PL1=15W - Silent mode
    ["quiet70"]="35 50 powersave balance_power quiet"           # PL1=35W - Fans max 70% (~3850RPM)
    ["balanced"]="50 65 performance performance balanced"       # PL1=50W - Balanced (Now Max Performance)
    ["performance"]="80 115 performance performance balanced"   # PL1=80W - Performance mode
    ["turbo"]="100 140 performance performance performance"     # PL1=100W - Maximum performance (Turbo Fans)
    ["extreme"]="115 160 performance performance performance"   # PL1=115W - Maximum (careful!)
)

# Fan monitoring paths (Acer WMI hwmon)
FAN1_PATH="/sys/class/hwmon/hwmon9/fan1_input"
FAN2_PATH="/sys/class/hwmon/hwmon9/fan2_input"
FAN_MAX_RPM=5500  # Approximate max RPM for Acer Predator fans

# Acer EC Platform Profile path (auto-detected)
PLATFORM_PROFILE_PATH=$(ls /sys/class/platform-profile/*/profile 2>/dev/null | head -n 1)

# EPP options: default, performance, balance_performance, balance_power, power

# Ensure we're running as root for write operations
check_root() {
    if [[ $EUID -ne 0 && "$1" != "status" && "$1" != "monitor" && "$1" != "help" && "$1" != "-h" && "$1" != "--help" ]]; then
        echo -e "${RED}Error: This command requires root privileges.${NC}"
        echo "Try: sudo $0 $*"
        exit 1
    fi
}

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Create config directory if needed
init_config() {
    mkdir -p "$(dirname "$CONFIG_FILE")"
    if [[ ! -f "$CONFIG_FILE" ]]; then
        cat > "$CONFIG_FILE" << 'EOF'
# TDP Manager Configuration
# Default profile to apply on boot
DEFAULT_PROFILE=performance
# Custom profiles (format: name=PL1,PL2)
# CUSTOM_gaming=70,100
EOF
    fi
}

# Read current power limits
get_current_power() {
    local pl1_uw=$(cat "${RAPL_PATH}/constraint_0_power_limit_uw" 2>/dev/null)
    local pl2_uw=$(cat "${RAPL_PATH}/constraint_1_power_limit_uw" 2>/dev/null)
    
    if [[ -z "$pl1_uw" ]]; then
        echo "Error reading RAPL values"
        return 1
    fi
    
    local pl1_w=$((pl1_uw / 1000000))
    local pl2_w=$((pl2_uw / 1000000))
    
    echo "$pl1_w $pl2_w"
}

# Read fan speeds (RPM)
get_fan_speeds() {
    local fan1_rpm=$(cat "$FAN1_PATH" 2>/dev/null)
    local fan2_rpm=$(cat "$FAN2_PATH" 2>/dev/null)
    
    if [[ -z "$fan1_rpm" ]]; then
        fan1_rpm=0
    fi
    if [[ -z "$fan2_rpm" ]]; then
        fan2_rpm=0
    fi
    
    echo "$fan1_rpm $fan2_rpm"
}

# Calculate fan percentage
get_fan_percentage() {
    local rpm=$1
    local percent=$((rpm * 100 / FAN_MAX_RPM))
    # Cap at 100%
    if [[ $percent -gt 100 ]]; then
        percent=100
    fi
    echo $percent
}

# Get energy consumption (for monitoring)
get_energy_consumption() {
    local energy_uj=$(cat "${RAPL_PATH}/energy_uj" 2>/dev/null)
    echo $((energy_uj / 1000000))  # Convert to joules
}

# Set power limits
set_power_limits() {
    local pl1=$1
    local pl2=$2
    
    # Validate inputs
    if [[ ! "$pl1" =~ ^[0-9]+$ ]] || [[ ! "$pl2" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}Error: Invalid power values${NC}"
        return 1
    fi
    
    # Safety checks
    if [[ $pl1 -gt 150 ]] || [[ $pl2 -gt 180 ]]; then
        echo -e "${RED}Warning: Power limits above 150W/180W are dangerous!${NC}"
        read -p "Are you sure you want to continue? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 1
        fi
    fi
    
    # Convert to microwatts
    local pl1_uw=$((pl1 * 1000000))
    local pl2_uw=$((pl2 * 1000000))
    
    echo -e "${CYAN}Setting PL1=${pl1}W, PL2=${pl2}W...${NC}"
    
    # Write to RAPL (order matters: set time window first if needed)
    echo $pl1_uw > "${RAPL_PATH}/constraint_0_power_limit_uw" 2>/dev/null
    echo $pl2_uw > "${RAPL_PATH}/constraint_1_power_limit_uw" 2>/dev/null
    
    # Verify the change
    local new_vals=$(get_current_power)
    local new_pl1=$(echo $new_vals | cut -d' ' -f1)
    local new_pl2=$(echo $new_vals | cut -d' ' -f2)
    
    if [[ "$new_pl1" == "$pl1" ]] && [[ "$new_pl2" == "$pl2" ]]; then
        echo -e "${GREEN}✓ Power limits set successfully!${NC}"
        log "Set PL1=${pl1}W PL2=${pl2}W"
        return 0
    else
        echo -e "${YELLOW}⚠ Power limits may have been clamped by hardware${NC}"
        echo "  Requested: PL1=${pl1}W PL2=${pl2}W"
        echo "  Actual:    PL1=${new_pl1}W PL2=${new_pl2}W"
        log "Set attempt: PL1=${pl1}W PL2=${pl2}W -> Actual: PL1=${new_pl1}W PL2=${new_pl2}W"
        return 1
    fi
}

# Set CPU governor (performance or powersave)
set_governor() {
    local governor=$1
    local cpu_count=$(nproc)
    
    echo -e "${CYAN}Setting governor to ${governor}...${NC}"
    
    for ((i=0; i<cpu_count; i++)); do
        echo "$governor" > /sys/devices/system/cpu/cpu${i}/cpufreq/scaling_governor 2>/dev/null
    done
    
    local current=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)
    if [[ "$current" == "$governor" ]]; then
        echo -e "${GREEN}✓ Governor set to ${governor}${NC}"
        log "Governor set to $governor"
        return 0
    else
        echo -e "${YELLOW}⚠ Could not set governor to ${governor}, current: ${current}${NC}"
        return 1
    fi
}

# Set Energy Performance Preference (EPP)
set_epp() {
    local epp=$1
    local cpu_count=$(nproc)
    
    # Check if EPP is supported
    if [[ ! -f /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference ]]; then
        echo -e "${YELLOW}⚠ EPP not supported on this system${NC}"
        return 1
    fi
    
    echo -e "${CYAN}Setting EPP to ${epp}...${NC}"
    
    for ((i=0; i<cpu_count; i++)); do
        echo "$epp" > /sys/devices/system/cpu/cpu${i}/cpufreq/energy_performance_preference 2>/dev/null
    done
    
    local current=$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)
    if [[ "$current" == "$epp" ]]; then
        echo -e "${GREEN}✓ EPP set to ${epp}${NC}"
        log "EPP set to $epp"
        return 0
    else
        echo -e "${YELLOW}⚠ Could not set EPP to ${epp}, current: ${current}${NC}"
        return 1
    fi
}

# Load acer_thermal_lite module if needed
load_facer_module() {
    if lsmod | grep -q "acer_thermal_lite"; then
        return 0
    fi
    
    echo -e "${CYAN}Attempting to load acer_thermal_lite module...${NC}"
    # Try the lite version first
    local mod_path="/home/felipeb/predator_power_linux/acer_thermal_lite/acer_thermal_lite.ko"
    if [[ -f "$mod_path" ]]; then
        if insmod "$mod_path" 2>/dev/null; then
            echo -e "${GREEN}✓ acer_thermal_lite loaded successfully!${NC}"
            sleep 0.5
            PLATFORM_PROFILE_PATH=$(ls /sys/class/platform-profile/*/profile 2>/dev/null | head -n 1)
            return 0
        fi
    fi

    # Fallback to standard facer if installed
    if modprobe facer predator_v4=1 2>/dev/null; then
        echo -e "${GREEN}✓ facer module loaded successfully!${NC}"
        sleep 1
        PLATFORM_PROFILE_PATH=$(ls /sys/class/platform-profile/*/profile 2>/dev/null | head -n 1)
        return 0
    else
        echo -e "${RED}✗ Failed to load Acer thermal modules.${NC}"
        echo -e "${YELLOW}Tip: Ensure acer_thermal_lite is compiled. Run: cd acer_thermal_lite && make${NC}"
        return 1
    fi
}

# Get current governor and EPP
get_cpu_settings() {
    local governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)
    local epp=$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)
    echo "$governor $epp"
}
# Set Acer EC Platform Profile (controls real TDP at hardware level)
set_platform_profile() {
    local profile=$1
    
    # Check if platform profile is available, try to load if not
    if [[ -z "$PLATFORM_PROFILE_PATH" || ! -f "$PLATFORM_PROFILE_PATH" ]]; then
        load_facer_module
        PLATFORM_PROFILE_PATH=$(ls /sys/class/platform-profile/*/profile 2>/dev/null | head -n 1)
    fi
    
    if [[ -z "$PLATFORM_PROFILE_PATH" || ! -f "$PLATFORM_PROFILE_PATH" ]]; then
        echo -e "${YELLOW}⚠ Platform profile still not available. Acer EC control disabled.${NC}"
        return 1
    fi

    
    echo -e "${CYAN}Setting Acer EC profile to ${profile}...${NC}"
    echo "$profile" > "$PLATFORM_PROFILE_PATH" 2>/dev/null
    
    local current=$(cat "$PLATFORM_PROFILE_PATH" 2>/dev/null)
    if [[ "$current" == "$profile" ]]; then
        echo -e "${GREEN}✓ Acer EC profile set to ${profile}${NC}"
        log "Platform profile set to $profile"
        return 0
    else
        echo -e "${YELLOW}⚠ Could not set platform profile to ${profile}, current: ${current}${NC}"
        return 1
    fi
}

# Get current platform profile
get_platform_profile() {
    if [[ -f "$PLATFORM_PROFILE_PATH" ]]; then
        cat "$PLATFORM_PROFILE_PATH" 2>/dev/null
    else
        echo "unavailable"
    fi
}

# Apply a profile
apply_profile() {
    local profile=$1
    
    if [[ -z "${PROFILES[$profile]}" ]]; then
        echo -e "${RED}Unknown profile: ${profile}${NC}"
        echo "Available profiles: ${!PROFILES[@]}"
        return 1
    fi
    
    local values=(${PROFILES[$profile]})
    local pl1=${values[0]}
    local pl2=${values[1]}
    local governor=${values[2]:-performance}
    local epp=${values[3]:-performance}
    local platform_profile=${values[4]:-balanced}
    
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  Applying profile: ${GREEN}${profile}${BLUE}              ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
    
    # Set Acer EC platform profile FIRST (this is the real limiter!)
    set_platform_profile "$platform_profile"
    
    # Set governor (this enables higher frequencies)
    set_governor "$governor"
    
    # Set EPP (this affects how aggressively the CPU boosts)
    set_epp "$epp"
    
    # Finally set RAPL power limits
    set_power_limits $pl1 $pl2
    
    echo ""
    echo -e "${GREEN}✓ Profile ${profile} applied!${NC}"
}

# Show current status
show_status() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║             TDP Manager - Intel i7-12700H                   ║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
    
    # CPU Model
    local cpu_model=$(cat /proc/cpuinfo | grep "model name" | head -1 | cut -d':' -f2 | xargs)
    echo -e "${CYAN}║${NC} CPU: ${GREEN}${cpu_model}${NC}"
    
    # Current power limits
    local current=$(get_current_power)
    local pl1=$(echo $current | cut -d' ' -f1)
    local pl2=$(echo $current | cut -d' ' -f2)
    
    echo -e "${CYAN}║${NC} Current PL1: ${YELLOW}${pl1}W${NC}"
    echo -e "${CYAN}║${NC} Current PL2: ${YELLOW}${pl2}W${NC}"
    
    # Governor and EPP
    local cpu_settings=$(get_cpu_settings)
    local governor=$(echo $cpu_settings | cut -d' ' -f1)
    local epp=$(echo $cpu_settings | cut -d' ' -f2)
    
    local gov_color=$GREEN
    [[ "$governor" == "powersave" ]] && gov_color=$YELLOW
    echo -e "${CYAN}║${NC} Governor: ${gov_color}${governor}${NC}"
    echo -e "${CYAN}║${NC} EPP: ${gov_color}${epp}${NC}"
    
    # Acer EC Platform Profile
    local platform=$(get_platform_profile)
    local plat_color=$GREEN
    [[ "$platform" == "quiet" ]] && plat_color=$YELLOW
    [[ "$platform" == "low-power" ]] && plat_color=$RED
    [[ "$platform" == "unavailable" ]] && plat_color=$RED
    echo -e "${CYAN}║${NC} Acer EC: ${plat_color}${platform}${NC}"
    
    # Detect current profile
    local detected_profile="custom"
    for profile in "${!PROFILES[@]}"; do
        local values=(${PROFILES[$profile]})
        if [[ "${values[0]}" == "$pl1" ]] && [[ "${values[1]}" == "$pl2" ]]; then
            detected_profile=$profile
            break
        fi
    done
    echo -e "${CYAN}║${NC} Profile: ${GREEN}${detected_profile}${NC}"

    
    # Temperature (if available)
    local temp_paths=$(find /sys/class/thermal -name "temp" -path "*thermal_zone*" 2>/dev/null | head -1)
    if [[ -n "$temp_paths" ]]; then
        local temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)
        if [[ -n "$temp" ]]; then
            local temp_c=$((temp / 1000))
            local temp_color=$GREEN
            [[ $temp_c -gt 70 ]] && temp_color=$YELLOW
            [[ $temp_c -gt 85 ]] && temp_color=$RED
            echo -e "${CYAN}║${NC} Temperature: ${temp_color}${temp_c}°C${NC}"
        fi
    fi
    
    # Current frequency
    local freq=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null)
    if [[ -n "$freq" ]]; then
        local freq_mhz=$((freq / 1000))
        local freq_ghz_int=$((freq_mhz / 1000))
        local freq_ghz_dec=$((freq_mhz % 1000 / 10))
        printf "${CYAN}║${NC} P-Core Freq: ${GREEN}%d.%02d GHz${NC}\n" $freq_ghz_int $freq_ghz_dec
    fi
    
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
    
    # Missing facer warning
    if [[ "$platform" == "unavailable" ]]; then
        echo -e "${CYAN}║${NC} ${YELLOW}⚠ WARNING: Acer EC module (facer) not found!${NC}"
        echo -e "${CYAN}║${NC}   Power will likely drop to 35W after some time.${NC}"
        echo -e "${CYAN}║${NC}   Try: sudo modprobe facer predator_v4=1${NC}"
        echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
    fi

    echo -e "${CYAN}║${NC} Available Profiles:${NC}"
    for profile in silent balanced performance turbo extreme; do
        local values=(${PROFILES[$profile]})
        local marker=" "
        [[ "$profile" == "$detected_profile" ]] && marker="*"
        printf "${CYAN}║${NC}   ${marker} %-12s PL1=%3dW  PL2=%3dW\n" "${profile}" "${values[0]}" "${values[1]}"
    done
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
}

# Daemon mode to keep settings applied
run_daemon() {
    local profile=$1
    local interval=${2:-10}
    
    if [[ -z "$profile" ]]; then
        echo -e "${RED}Error: Profile name required for daemon mode${NC}"
        echo "Usage: sudo $0 daemon <profile> [interval]"
        return 1
    fi
    
    if [[ -z "${PROFILES[$profile]}" ]]; then
        echo -e "${RED}Unknown profile: ${profile}${NC}"
        return 1
    fi
    
    echo -e "${BLUE}Starting TDP Manager Daemon...${NC}"
    echo -e "Profile: ${GREEN}${profile}${NC}"
    echo -e "Interval: ${interval}s"
    
    # Apply once at start
    apply_profile "$profile"
    
    while true; do
        sleep $interval
        
        # Check current values
        local current=$(get_current_power)
        local pl1=$(echo $current | cut -d' ' -f1)
        
        local target_values=(${PROFILES[$profile]})
        local target_pl1=${target_values[0]}
        
        if [[ "$pl1" != "$target_pl1" ]]; then
            echo "[$(date '+%H:%M:%S')] ⚠ Power limit reset detected (${pl1}W -> ${target_pl1}W). Re-applying..."
            apply_profile "$profile" > /dev/null
        fi
    done
}


# Real-time power monitor
monitor_power() {
    local interval=${1:-1}
    echo -e "${CYAN}Power Monitor (Ctrl+C to exit)${NC}"
    echo -e "${CYAN}════════════════════════════════${NC}"
    
    local prev_energy=$(get_energy_consumption)
    
    while true; do
        sleep $interval
        local curr_energy=$(get_energy_consumption)
        local power=$((curr_energy - prev_energy))
        prev_energy=$curr_energy
        
        local current=$(get_current_power)
        local pl1=$(echo $current | cut -d' ' -f1)
        
        # Temperature
        local temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)
        local temp_c=$((temp / 1000))
        
        # Frequency
        local freq=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null)
        local freq_mhz=$((freq / 1000))
        local freq_ghz_int=$((freq_mhz / 1000))
        local freq_ghz_dec=$((freq_mhz % 1000 / 10))
        
        printf "\r%s | Power: %3dW (limit: %3dW) | Temp: %2d°C | Freq: %d.%02dGHz   " \
            "$(date '+%H:%M:%S')" "$power" "$pl1" "$temp_c" "$freq_ghz_int" "$freq_ghz_dec"
    done
}

# Show help
show_help() {
    cat << 'EOF'
TDP Manager for Intel 12th Gen CPUs
====================================

Usage: tdp-manager.sh [COMMAND] [OPTIONS]

Commands:
  status              Show current power configuration (no root needed)
  monitor [interval]  Live power monitoring (no root needed)
  daemon <profile>    Run in background to keep limits applied
  facer install       Install/Configure module persistence
  facer build         Download and compile the facer module source
  set <PL1> <PL2>     Set custom power limits (in watts)


  profile <name>      Apply a power profile (TDP + governor + EPP)

  governor <mode>     Set CPU governor (performance|powersave)
  epp <mode>          Set Energy Performance Preference
  list                List available profiles
  boot <profile>      Set profile to apply on boot
  service install     Install systemd service
  service remove      Remove systemd service
  help, -h, --help    Show this help message

Examples:
  sudo tdp-manager.sh set 60 80           # Set PL1=60W, PL2=80W
  sudo tdp-manager.sh profile performance # Apply performance profile
  sudo tdp-manager.sh governor performance# Set governor to performance
  sudo tdp-manager.sh epp performance     # Set EPP to performance
  tdp-manager.sh status                   # Show current status
  tdp-manager.sh monitor 2                # Monitor power every 2 seconds

Profiles (TDP + Governor + EPP):
  silent       PL1=15W   PL2=25W   powersave + power
  balanced     PL1=45W   PL2=65W   powersave + balance_performance  
  performance  PL1=80W   PL2=115W  performance + performance
  turbo        PL1=100W  PL2=140W  performance + performance
  extreme      PL1=115W  PL2=160W  performance + performance

Governor Options:
  performance  - CPU runs at maximum frequency
  powersave    - CPU scales frequency based on load

EPP Options (Energy Performance Preference):
  performance          - Maximum performance, highest power
  balance_performance  - Favor performance
  balance_power        - Favor power saving
  power                - Maximum power saving

Notes:
- Changes are temporary and reset on reboot
- Use 'service install' for persistent settings
- Governor affects frequency, EPP affects boost behavior
- Higher TDP = more heat = potentially shorter lifespan
EOF
}

# Install systemd service
install_service() {
    local profile=${1:-"performance"}
    local script_path=$(readlink -f "$0")
    
    cat > /etc/systemd/system/tdp-manager.service << EOF
[Unit]
Description=TDP Manager - Intel Power Limit Control
After=multi-user.target turbo-fan.service
Wants=turbo-fan.service

[Service]
Type=oneshot
# Wait for facer module to initialize platform profile
ExecStartPre=/bin/sleep 2
ExecStart=${script_path} profile ${profile}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable tdp-manager.service
    
    echo -e "${GREEN}✓ Service installed!${NC}"
    echo "  Profile '${profile}' will be applied on each boot."
    echo "  Depends on: turbo-fan.service (facer module)"
    echo "  To start now: sudo systemctl start tdp-manager"
    echo "  To check status: systemctl status tdp-manager"
}

# Remove systemd service
remove_service() {
    systemctl disable tdp-manager.service 2>/dev/null
    rm -f /etc/systemd/system/tdp-manager.service
    systemctl daemon-reload
    
    echo -e "${GREEN}✓ Service removed${NC}"
}

# Install/Configure Acer thermal module persistence
setup_facer() {
    echo -e "${BLUE}Configuring acer_thermal_lite module persistence...${NC}"
    
    # 1. Add to modules-load
    echo "acer_thermal_lite" | tee /etc/modules-load.d/acer_thermal_lite.conf > /dev/null
    
    # Remove old facer configs
    rm -f /etc/modprobe.d/facer.conf /etc/modules-load.d/facer.conf
    
    # 2. Try to load now
    modprobe acer_thermal_lite 2>/dev/null
    
    if lsmod | grep -q "acer_thermal_lite"; then
        echo -e "${GREEN}✓ acer_thermal_lite configured correctly and loaded!${NC}"
    else
        echo -e "${YELLOW}⚠ Configured but could not load. Missing the module file?${NC}"
        echo -e "${CYAN}Try: sudo $0 facer build${NC}"
    fi
}

# Compile and install the acer_thermal_lite module
build_facer() {
    echo -e "${BLUE}Starting Acer Thermal Lite build process...${NC}"
    
    local compiler="gcc"
    local make_opts=""
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local src_dir="${script_dir}/acer_thermal_lite"
    
    # Detect if kernel was built with clang (common on CachyOS)
    if grep -q "clang" /proc/version; then
        echo -e "${YELLOW}Detected Clang-built kernel. Will use LLVM toolchain for compilation.${NC}"
        compiler="clang"
        make_opts="LLVM=1"
    fi

    # Detect package manager for dependencies
    if command -v pacman &> /dev/null; then
        echo -e "${CYAN}Installing dependencies via pacman...${NC}"
        local deps="linux-headers make gcc"
        [[ "$compiler" == "clang" ]] && deps="$deps clang lld"
        pacman -Sy --needed --noconfirm $deps
    elif command -v apt-get &> /dev/null; then
        echo -e "${CYAN}Installing dependencies via apt...${NC}"
        local deps="linux-headers-$(uname -r) make gcc"
        [[ "$compiler" == "clang" ]] && deps="$deps clang lld"
        apt-get update && apt-get install -y $deps
    fi

    if [[ ! -d "$src_dir" ]]; then
        echo -e "${RED}✗ Source directory not found at $src_dir${NC}"
        return 1
    fi
    
    cd "$src_dir" || return 1
    
    echo -e "${CYAN}Compiling module with ${compiler}...${NC}"
    make clean && make $make_opts
    
    if [[ -f "acer_thermal_lite.ko" ]]; then
        echo -e "${CYAN}Installing module to kernel...${NC}"
        local mod_path="/lib/modules/$(uname -r)/extra"
        mkdir -p "$mod_path"
        cp acer_thermal_lite.ko "$mod_path/"
        depmod -a
        
        echo -e "${GREEN}✓ acer_thermal_lite compiled and installed!${NC}"
        setup_facer
    else
        echo -e "${RED}✗ Compilation failed. Please check build errors above.${NC}"
        return 1
    fi
}



# List profiles

list_profiles() {
    echo -e "${CYAN}Available Power Profiles${NC}"
    echo "========================="
    for profile in silent balanced performance turbo extreme; do
        local values=(${PROFILES[$profile]})
        printf "  %-12s PL1=%3dW  PL2=%3dW\n" "${profile}" "${values[0]}" "${values[1]}"
    done
}

# Main function
main() {
    init_config
    
    case "${1:-status}" in
        status)
            show_status
            ;;
        monitor)
            monitor_power "${2:-1}"
            ;;
        daemon)
            check_root "$1"
            run_daemon "$2" "${3:-10}"
            ;;
        facer)
            check_root "$1"
            case "$2" in
                install|setup)
                    setup_facer
                    ;;
                build|compile)
                    build_facer
                    ;;
                *)
                    echo "Usage: $0 facer [install|build]"
                    ;;
            esac
            ;;

        set)


            check_root "$1"
            set_power_limits "$2" "$3"
            ;;
        profile)
            check_root "$1"
            apply_profile "$2"
            ;;
        governor)
            check_root "$1"
            set_governor "$2"
            ;;
        epp)
            check_root "$1"
            set_epp "$2"
            ;;
        list)
            list_profiles
            ;;
        service)
            check_root "$1"
            case "$2" in
                install)
                    install_service "$3"
                    ;;
                remove)
                    remove_service
                    ;;
                *)
                    echo "Usage: service [install|remove] [profile]"
                    ;;
            esac
            ;;
        boot)
            check_root "$1"
            install_service "$2"
            ;;
        help|-h|--help)
            show_help
            ;;
        *)
            echo "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
