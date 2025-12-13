#!/bin/bash
# Mini CPU Benchmark - Stress test with monitoring
# Usage: ./benchmark.sh [duration_seconds]

DURATION=${1:-30}
RAPL_PATH="/sys/class/powercap/intel-rapl/intel-rapl:0"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Get CPU count
CPU_COUNT=$(nproc)

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║          Mini CPU Benchmark - Intel i7-12700H                 ║${NC}"
echo -e "${CYAN}╠════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC} Duration: ${GREEN}${DURATION}s${NC} | CPUs: ${GREEN}${CPU_COUNT}${NC} | Governor: ${GREEN}$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Start stress workers
echo -e "${YELLOW}Starting ${CPU_COUNT} stress workers...${NC}"
for ((i=0; i<CPU_COUNT; i++)); do
    yes > /dev/null &
done

# Get initial energy reading
ENERGY_START=$(cat "${RAPL_PATH}/energy_uj" 2>/dev/null)

# Arrays to store readings
declare -a TEMPS
declare -a FREQS
declare -a POWERS

echo ""
echo -e "${CYAN}Time   | Temp  | Freq (P-Core) | Power | Status${NC}"
echo -e "${CYAN}-------|-------|---------------|-------|--------${NC}"

# Monitor loop
PREV_ENERGY=$ENERGY_START

for ((sec=1; sec<=DURATION; sec++)); do
    sleep 1
    
    # Current energy
    CURR_ENERGY=$(cat "${RAPL_PATH}/energy_uj" 2>/dev/null)
    POWER=$(( (CURR_ENERGY - PREV_ENERGY) / 1000000 ))
    PREV_ENERGY=$CURR_ENERGY
    
    # Temperature (find CPU package temp)
    TEMP=0
    for zone in /sys/class/thermal/thermal_zone*/; do
        TYPE=$(cat "${zone}type" 2>/dev/null)
        if [[ "$TYPE" == *"x86_pkg"* ]] || [[ "$TYPE" == *"Package"* ]]; then
            TEMP=$(( $(cat "${zone}temp" 2>/dev/null) / 1000 ))
            break
        fi
    done
    # Fallback
    [[ $TEMP -eq 0 ]] && TEMP=$(( $(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null) / 1000 ))
    
    # Find max P-Core frequency (cores 0-5 are P-cores on 12700H)
    MAX_FREQ=0
    for cpu in 0 1 2 3 4 5; do
        FREQ=$(cat /sys/devices/system/cpu/cpu${cpu}/cpufreq/scaling_cur_freq 2>/dev/null)
        [[ $FREQ -gt $MAX_FREQ ]] && MAX_FREQ=$FREQ
    done
    
    # Convert to GHz (without bc)
    FREQ_MHZ=$((MAX_FREQ / 1000))
    FREQ_GHZ_INT=$((FREQ_MHZ / 1000))
    FREQ_GHZ_DEC=$(( (FREQ_MHZ % 1000) / 10 ))
    
    # Store values
    TEMPS+=($TEMP)
    FREQS+=($MAX_FREQ)
    POWERS+=($POWER)
    
    # Temperature color
    TEMP_COLOR=$GREEN
    [[ $TEMP -gt 75 ]] && TEMP_COLOR=$YELLOW
    [[ $TEMP -gt 90 ]] && TEMP_COLOR=$RED
    
    # Status
    STATUS="Running"
    [[ $TEMP -gt 90 ]] && STATUS="HOT!"
    [[ $TEMP -gt 100 ]] && STATUS="THROTTLE!"
    
    printf "${CYAN}%3ds${NC}   | ${TEMP_COLOR}%3d°C${NC} | %d.%02d GHz     | %3dW  | %s\n" \
        "$sec" "$TEMP" "$FREQ_GHZ_INT" "$FREQ_GHZ_DEC" "$POWER" "$STATUS"
done

# Stop stress workers
echo ""
echo -e "${YELLOW}Stopping stress workers...${NC}"
pkill -P $$ 2>/dev/null
killall yes 2>/dev/null
sleep 1

# Calculate statistics
ENERGY_END=$(cat "${RAPL_PATH}/energy_uj" 2>/dev/null)
TOTAL_ENERGY=$(( (ENERGY_END - ENERGY_START) / 1000000 ))

# Calculate averages and max
TEMP_SUM=0
TEMP_MAX=0
FREQ_SUM=0
FREQ_MAX=0
POWER_SUM=0
POWER_MAX=0

for i in "${!TEMPS[@]}"; do
    TEMP_SUM=$((TEMP_SUM + TEMPS[i]))
    [[ ${TEMPS[i]} -gt $TEMP_MAX ]] && TEMP_MAX=${TEMPS[i]}
    
    FREQ_SUM=$((FREQ_SUM + FREQS[i]))
    [[ ${FREQS[i]} -gt $FREQ_MAX ]] && FREQ_MAX=${FREQS[i]}
    
    POWER_SUM=$((POWER_SUM + POWERS[i]))
    [[ ${POWERS[i]} -gt $POWER_MAX ]] && POWER_MAX=${POWERS[i]}
done

COUNT=${#TEMPS[@]}
TEMP_AVG=$((TEMP_SUM / COUNT))
FREQ_AVG=$((FREQ_SUM / COUNT))
POWER_AVG=$((POWER_SUM / COUNT))

# Convert frequencies to GHz
FREQ_AVG_MHZ=$((FREQ_AVG / 1000))
FREQ_AVG_GHZ_INT=$((FREQ_AVG_MHZ / 1000))
FREQ_AVG_GHZ_DEC=$(( (FREQ_AVG_MHZ % 1000) / 10 ))

FREQ_MAX_MHZ=$((FREQ_MAX / 1000))
FREQ_MAX_GHZ_INT=$((FREQ_MAX_MHZ / 1000))
FREQ_MAX_GHZ_DEC=$(( (FREQ_MAX_MHZ % 1000) / 10 ))

echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                      BENCHMARK RESULTS                        ║${NC}"
echo -e "${CYAN}╠════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC} Duration:        ${GREEN}${DURATION} seconds${NC}"
echo -e "${CYAN}║${NC} Total Energy:    ${GREEN}${TOTAL_ENERGY} Joules${NC}"
echo -e "${CYAN}╠════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}                    ${YELLOW}Average${NC}         ${RED}Maximum${NC}"
echo -e "${CYAN}║${NC} Temperature:     ${YELLOW}${TEMP_AVG}°C${NC}            ${RED}${TEMP_MAX}°C${NC}"
printf "${CYAN}║${NC} P-Core Freq:     ${YELLOW}%d.%02d GHz${NC}       ${RED}%d.%02d GHz${NC}\n" \
    "$FREQ_AVG_GHZ_INT" "$FREQ_AVG_GHZ_DEC" "$FREQ_MAX_GHZ_INT" "$FREQ_MAX_GHZ_DEC"
echo -e "${CYAN}║${NC} Power Draw:      ${YELLOW}${POWER_AVG}W${NC}             ${RED}${POWER_MAX}W${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"

# Verdict
echo ""
if [[ $TEMP_MAX -lt 85 ]]; then
    echo -e "${GREEN}✓ Excellent! Thermals are well under control.${NC}"
elif [[ $TEMP_MAX -lt 95 ]]; then
    echo -e "${YELLOW}⚠ Good, but temperatures are getting warm.${NC}"
else
    echo -e "${RED}⚠ Warning: High temperatures detected. Consider reducing TDP.${NC}"
fi

if [[ $POWER_MAX -ge 60 ]]; then
    echo -e "${GREEN}✓ Power delivery is working correctly! (~${POWER_MAX}W)${NC}"
else
    echo -e "${YELLOW}⚠ Power limited to ${POWER_MAX}W. Expected 60W+ for this CPU.${NC}"
fi
