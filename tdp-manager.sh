#!/bin/bash
# Predator Power Manager - Simplified
# Controls CPU TDP (PL1/PL2) and Fan Boost on Acer Predator

RAPL_PATH="/sys/class/powercap/intel-rapl/intel-rapl:0"
FAN_BOOST_PATH="/sys/devices/platform/acer-thermal-lite/fan_boost"
PROFILE_FILE="/tmp/predator_profile"
CONFIG_DIR="${HOME}/.config/predator-power"

# Profiles: PL1 PL2 platform_profile
declare -A PROFILES=(
    ["balanced"]="50 65 balanced"
    ["performance"]="80 115 balanced-performance"
    ["turbo"]="100 140 performance"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_root() {
    [[ $EUID -eq 0 ]] && return
    echo "Relaunching with pkexec..."
    exec pkexec "$0" "$@"
}

stop_conflicting_daemons() {
    if systemctl is-active --quiet power-profiles-daemon 2>/dev/null; then
        echo -e "${YELLOW}Stopping power-profiles-daemon (conflicts with TDP control)...${NC}"
        systemctl stop power-profiles-daemon 2>/dev/null
    fi
}

set_power() {
    local pl1=$1 pl2=$2
    echo $((pl1 * 1000000)) > "${RAPL_PATH}/constraint_0_power_limit_uw"
    echo $((pl2 * 1000000)) > "${RAPL_PATH}/constraint_1_power_limit_uw"
    echo -e "${GREEN}PL1=${pl1}W PL2=${pl2}W${NC}"
}

set_platform() {
    local profile=$1
    local path=$(ls /sys/class/platform-profile/*/profile 2>/dev/null | head -n 1)
    [[ -n "$path" ]] && echo "$profile" > "$path"
}

set_fanboost() {
    local state=$1
    if [[ $state -eq 1 ]]; then
        # Fan boost requires performance platform profile on most Predators
        set_platform "performance"
        echo 1 > "$FAN_BOOST_PATH"
    else
        echo 0 > "$FAN_BOOST_PATH"
        # Restore the platform profile associated with the current TDP profile
        local cur_name=$(cat "$PROFILE_FILE" 2>/dev/null || echo "balanced")
        local vals=(${PROFILES[$cur_name]})
        [[ -n "${vals[2]}" ]] && set_platform "${vals[2]}"
    fi
    echo -e "${GREEN}Fan Boost: $([ $state -eq 1 ] && echo ON || echo OFF)${NC}"
}

apply_profile() {
    local name=$1
    local vals=(${PROFILES[$name]})
    [[ ${#vals[@]} -eq 0 ]] && { echo -e "${RED}Unknown: $name${NC}"; exit 1; }

    # Save current profile name first
    echo "$name" > "$PROFILE_FILE"

    stop_conflicting_daemons
    set_power "${vals[0]}" "${vals[1]}"

    # Check if fan boost is already ON
    local fan=$(cat "$FAN_BOOST_PATH" 2>/dev/null)
    if [[ "$fan" == "1" ]]; then
        # Keep it ON (requires performance platform)
        set_platform "performance"
    else
        # Use the profile's default platform
        set_platform "${vals[2]}"
    fi

    # Auto-enable fan boost for turbo profile
    [[ "$name" == "turbo" ]] && set_fanboost 1

    mkdir -p "$CONFIG_DIR"
    echo "$name" > "$CONFIG_DIR/last_profile"
    echo -e "${GREEN}Profile: $name${NC}"
}

show_status() {
    local pl1_uw=$(cat "${RAPL_PATH}/constraint_0_power_limit_uw" 2>/dev/null)
    local pl2_uw=$(cat "${RAPL_PATH}/constraint_1_power_limit_uw" 2>/dev/null)
    local pl1=$((pl1_uw / 1000000))
    local pl2=$((pl2_uw / 1000000))
    local fan=$(cat "$FAN_BOOST_PATH" 2>/dev/null)
    local platform=$(ls /sys/class/platform-profile/*/profile 2>/dev/null | head -n 1)
    local ec=$(cat "$platform" 2>/dev/null || echo "N/A")

    echo -e "${CYAN}=== Predator Power ===${NC}"
    echo -e "  PL1: ${YELLOW}${pl1}W${NC}  PL2: ${YELLOW}${pl2}W${NC}"
    echo -e "  Fan Boost: $([ "$fan" == "1" ] && echo -e "${GREEN}ON${NC}" || echo -e "${YELLOW}OFF${NC}")"
    echo -e "  EC: ${ec}"
}

install_service() {
    local profile=${1:-balanced}
    local bin=${2:-$(readlink -f "$0")}

    cat > /etc/systemd/system/predator-power.service << EOF
[Unit]
Description=Predator Power Manager
After=multi-user.target

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 3
ExecStart=${bin} profile ${profile}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable predator-power.service
    systemctl start predator-power.service
    echo -e "${GREEN}Service installed: profile '${profile}' on boot${NC}"
}

remove_service() {
    systemctl stop predator-power.service 2>/dev/null
    systemctl disable predator-power.service 2>/dev/null
    rm -f /etc/systemd/system/predator-power.service
    systemctl daemon-reload
    echo -e "${GREEN}Service removed${NC}"
}

case "${1:-status}" in
    set)       check_root; stop_conflicting_daemons; set_power "$2" "$3" ;;
    fanboost)  check_root; set_fanboost "$2" ;;
    profile)   check_root; apply_profile "$2" ;;
    status)    show_status ;;
    list)      echo "Profiles: ${!PROFILES[@]}" ;;
    service)   check_root; [[ "$2" == "remove" ]] && remove_service || install_service "$2" "$3" ;;
    *)         echo "Usage: $0 {set|fanboost|profile|status|list|service} [args]" ;;
esac
