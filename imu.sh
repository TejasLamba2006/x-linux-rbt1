#!/bin/sh

##############################################################################
# @file   lis3dsh.sh
# @brief  LIS3DSH IMU script for STM32MP257
#         Hardware: I2C8 (mapped to /dev/i2c-0)
##############################################################################

# --- Hardware Configuration ---
I2C_BUS=1                 # Mapped to I2C8 on your board
DEVICE_ADDR=0x1e          # Default address (try 0x1d if 0x1e fails)
is_config_done="false"

# Registers
REG_WHO_AM_I=0x0F         # Expected: 0x3F (63)
REG_CTRL4=0x20            # ODR & Axis Enable
REG_CTRL5=0x24            # Full Scale
REG_CTRL6=0x25            # BDU & Addr Inc
REG_STATUS=0x27           # Status register
OUT_X_L=0x28              # Start of data

# Sensitivity for ±2g scale = 0.06 mg/LSB
# We use 60/1000 in integer math
SENS_X1000=60 

# --- Helper Functions ---

# Read a single byte and convert from hex to decimal
read_reg() {
    val=$(i2cget -y "$I2C_BUS" "$DEVICE_ADDR" "$1")
    [ $? -ne 0 ] && return 1
    echo "$((val))"
}

# Write a byte (value in hex or dec)
write_reg() {
    i2cset -y "$I2C_BUS" "$DEVICE_ADDR" "$1" "$2"
}

lis3dsh_config() {
    if [ "$is_config_done" = "true" ]; then return 0; fi

    # 1. WHO_AM_I Check
    wai=$(read_reg "$REG_WHO_AM_I")
    if [ "$wai" -ne 63 ]; then
        echo "Error: LIS3DSH not found at $DEVICE_ADDR on Bus $I2C_BUS (Got $wai, expected 63)"
        exit 1
    fi

    # 2. Setup Device
    # CTRL_REG6 (0x25): BDU=1 (prevents partial reads), ADD_INC=1 (auto-increment)
    write_reg "$REG_CTRL6" 0x18
    
    # CTRL_REG5 (0x24): Full Scale = ±2g (0x00)
    write_reg "$REG_CTRL5" 0x00
    
    # CTRL_REG4 (0x20): ODR = 100Hz (0x60), Enable X,Y,Z axes (0x07) -> 0x67
    write_reg "$REG_CTRL4" 0x67

    sleep 0.05
    is_config_done="true"
}

lis3dsh_read_accel() {
    # Read Low and High bytes for X, Y, Z
    xl=$(read_reg 0x28); xh=$(read_reg 0x29)
    yl=$(read_reg 0x2A); yh=$(read_reg 0x2B)
    zl=$(read_reg 0x2C); zh=$(read_reg 0x2D)

    # Combine into 16-bit signed integers
    sx=$(( (xh << 8) | xl )); [ $sx -ge 32768 ] && sx=$((sx - 65536))
    sy=$(( (yh << 8) | yl )); [ $sy -ge 32768 ] && sy=$((sy - 65536))
    sz=$(( (zh << 8) | zl )); [ $sz -ge 32768 ] && sz=$((sz - 65536))

    # Convert to milli-g
    xmg=$(( sx * SENS_X1000 / 1000 ))
    ymg=$(( sy * SENS_X1000 / 1000 ))
    zmg=$(( sz * SENS_X1000 / 1000 ))

    echo "$xmg $ymg $zmg"
}

# --- Execution Modes ---

case "$1" in
    test)
        lis3dsh_config
        res=$(lis3dsh_read_accel)
        echo "LIS3DSH [Bus $I2C_BUS]: Success!"
        echo "X Y Z (mg): $res"
        ;;

    print)
        # Numerical print mode (good for logging)
        lis3dsh_config
        echo "Timestamp(s)  X(mg)  Y(mg)  Z(mg)"
        while :; do
            res=$(lis3dsh_read_accel)
            # Add simple timestamp using date
            echo "$(date +%s) $res"
            sleep 0.1
        done
        ;;

    stream)
        # Visual formatted output
        lis3dsh_config
        echo "Streaming data... Press Ctrl+C to stop"
        while :; do
            set -- $(lis3dsh_read_accel)
            printf "\r\033[KACCEL: X:%6d | Y:%6d | Z:%6d (mg)" "$1" "$2" "$3"
            sleep 0.1
        done
        ;;

    *)
        echo "Usage: $0 {test|print|stream}"
        echo "  test   - Verify sensor connection and read once"
        echo "  print  - Continuous numerical output with timestamps"
        echo "  stream - Continuous formatted output on one line"
        exit 1
        ;;
esac