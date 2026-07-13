#!/bin/sh

##
##############################################################################
# @file   lsm6dsv16x.sh
# @author SRA-SAIL, Noida
# @brief  LSM6DSV16X quick test (accelerometer only, ±2 g, 120 Hz, high-perf)
##############################################################################
# @attention
#
# Copyright (c) 2025 STMicroelectronics.
# All rights reserved.
#
# This software is licensed under terms that can be found in the LICENSE file
# in the root directory of this software component.
# If no LICENSE file comes with this software, it is provided AS-IS.
#
##############################################################################
##

#  – Verifies WHO_AM_I
#  – Enables BDU + auto-increment
#  – Reads one sample and prints it in mg

source ./board_utils.sh

is_lsm6dsv16x_config_done="false"

lsm6dsv16x_read_whoami() {
	local I2C_BUS=$I2C_BUS_PRIMARY
	local DEVICE_ADDR=$DEVICE_ADDR_LSM6DV16X
	local WHO_AM_I=0x0F
	# Read WHO_AM_I register
	whoami=$(utils_i2c_read_byte "$I2C_BUS" "$DEVICE_ADDR" "$WHO_AM_I")
	if [ $? -ne 0 ]; then
		utils_print_error "LSM6DSV16X - Failed to read register"
		return 1
	fi

	utils_print_debug "LSM6DSV16X: WHO_AM_I=$whoami"

	if [ "$whoami" -ne 112 ]; then
		utils_print_error "LSM6DSV16X: WHO_AM_I=$whoami (expected 112)"
		return 1
	fi

	echo $whoami
	return 0
}

lsm6dsv16x_config() {
	local CTRL3=0x12         # BDU | IF_INC bits default to 0x44
	local CTRL1=0x10         # ODR / OP_MODE (accelerometer)
	local CTRL8=0x17         # FS_XL bits (accelerometer full-scale)
	local I2C_BUS=$I2C_BUS_PRIMARY
	local DEVICE_ADDR=$DEVICE_ADDR_LSM6DV16X

	if [ "$is_lsm6dsv16x_config_done" = "true" ]; then
		utils_print_debug "LSM6DSV16X already configured"
		return 0
	fi
	# Keep default 0x44 (BDU=1, IF_INC=1) so multi-byte reads are coherent
	utils_i2c_write "$I2C_BUS" "$DEVICE_ADDR" "$CTRL3" 0x44

	if [ $? -ne 0 ]; then
		utils_print_error "LSM6DSV16X - Failed to write register"
		return 1
	fi
	# Select ±2 g full scale (FS_XL=00)
	utils_i2c_write "$I2C_BUS" "$DEVICE_ADDR" "$CTRL8" 0x00

	# High-performance mode, ODR=120 Hz (ODR_XL=0110, OP_MODE_XL=000)
	utils_i2c_write "$I2C_BUS" "$DEVICE_ADDR" "$CTRL1" 0x06

	# Allow filters to settle
	sleep 0.05
	is_lsm6dsv16x_config_done="true"
}

lsm6dsv16x_read_accel() {
	local I2C_BUS=$I2C_BUS_PRIMARY
	local DEVICE_ADDR=$DEVICE_ADDR_LSM6DV16X

	local OUTX_L_A=0x28 ; OUTX_H_A=0x29
	local OUTY_L_A=0x2A ; OUTY_H_A=0x2B
	local OUTZ_L_A=0x2C ; OUTZ_H_A=0x2D

	local SENS_MG=61         # 0.061 mg/LSB @ ±2 g

	local xL xH yL yH zL zH
	local sx sy sz xmg ymg zmg

	# Read 6 bytes of data from the accelerometer
	xL=$(utils_i2c_read_byte "$I2C_BUS" "$DEVICE_ADDR" "$OUTX_L_A")

	if [ $? -ne 0 ]; then
		utils_print_error "LSM6DSV16X - Failed to read register"
		return 1
	fi

	xH=$(utils_i2c_read_byte "$I2C_BUS" "$DEVICE_ADDR" "$OUTX_H_A")
	yL=$(utils_i2c_read_byte "$I2C_BUS" "$DEVICE_ADDR" "$OUTY_L_A")
	yH=$(utils_i2c_read_byte "$I2C_BUS" "$DEVICE_ADDR" "$OUTY_H_A")
	zL=$(utils_i2c_read_byte "$I2C_BUS" "$DEVICE_ADDR" "$OUTZ_L_A")
	zH=$(utils_i2c_read_byte "$I2C_BUS" "$DEVICE_ADDR" "$OUTZ_H_A")
	#

	# ---------- compose signed 16-bit words --------------------------------------
	sx=$(( (xH << 8) | xL )); [ $sx -ge 32768 ] && sx=$((sx - 65536))
	sy=$(( (yH << 8) | yL )); [ $sy -ge 32768 ] && sy=$((sy - 65536))
	sz=$(( (zH << 8) | zL )); [ $sz -ge 32768 ] && sz=$((sz - 65536))


	# ---------- convert to milli-g --------------------------------
	xmg=$(( sx * SENS_MG / 1000 ))
	ymg=$(( sy * SENS_MG / 1000 ))
	zmg=$(( sz * SENS_MG / 1000 ))

	printf '%d %d %d\n' "$xmg" "$ymg" "$zmg"
}

# check if the sensor is placed horizontally (900 < Z < 1100)
read_accel_horizontal() {
	lsm6dsv16x_config              # put sensor in 120 Hz HP mode

	# read one sample
	accel_data=$(lsm6dsv16x_read_accel)

	set -- $accel_data
	xval=$1  yval=$2  zval=$3

	if [ "$zval" -gt 900 ] && [ "$zval" -lt 1100 ]; then
		utils_print_debug "IMU is placed horizontally"
		return 0
	else
		utils_print_debug "IMU is not placed horizontally"
		return 1
	fi
}

# keep polling the sensor until it is inverted (horizontally)
read_accel_await_inversion() {
	local TIMEOUT=10
	local INTERVAL=0.2
	#local START_TIME=$(date +%s)

	lsm6dsv16x_config              # put sensor in 120 Hz HP mode

	while :; do
		accel_data=$(lsm6dsv16x_read_accel)

		set -- $accel_data
		xval=$1  yval=$2  zval=$3

		if [ "$zval" -lt -500 ] && [ "$zval" -gt -1100 ]; then
			printf "    Z Axis inversion successfully detected\n"
			utils_print_debug "IMU is inverted"
			return 0
		fi

		sleep $INTERVAL

		# check if timeout expired
		# if [ $(( $(date +%s) - START_TIME )) -ge $TIMEOUT ]; then
		# 	utils_print_debug "Timeout expired"
		# 	return 1
		# fi

		read -t 1 -n 1 key
        if [ $? -eq 0 ] && { [ "$key" = "n" ] || [ "$key" = "N" ]; }; then
            return 1
        fi
	done
}

show_accel_bars() {
	rate=${1:-5}                # samples per second
	interval=$(awk "BEGIN { printf \"%.3f\", 1/$rate }")

	# '~2g' gives about ±2000mg → choose bar half width 40 chars (50 mg/char)
	scale=50                    # mg per column
	width=40                    # half width of bar (+40, 0, -40)

	while :; do
		set -- $(lsm6dsv16x_read_accel)  # $1=X  $2=Y  $3=Z  (mg)

		x=$1 y=$2 z=$3

		# helper prints one axis in colour
		print_axis() {          # $1=value  $2=color-code
			v=$1 ; colour=$2
			chars=$(( v / scale ))
			# clamp to ±width
			[ $chars -gt  $width ] && chars=$width
			[ $chars -lt -$width ] && chars=-$width

			pos=$chars  # signed
			neg=$(( -pos ))

			# left (negative) side
			printf '\033[%sm' "$colour"
			while [ $neg -gt 0 ]; do printf '<'; neg=$((neg-1)); done
			printf '\033[0m'

			# centre zero marker
			printf '|'

			# right (positive) side
			printf '\033[%sm' "$colour"
			while [ $pos -gt 0 ]; do printf '>'; pos=$((pos-1)); done
			printf '\033[0m'
		}

		printf '\r\033[K'    # return & clear line
		printf 'X:' ; print_axis "$x" 31   # red
		printf '  Y:' ; print_axis "$y" 32 # green
		printf '  Z:' ; print_axis "$z" 34 # blue
		printf '   (%4d %4d %4d mg)' "$x" "$y" "$z"

		# sleep interval using POSIX awk (dash's sleep supports fractions too)
		awk "BEGIN { system(\"sleep $interval\") }" </dev/null
	done
}


if [ "$1" = "test" ]; then
	echo ">>>Testing LSM6DSV16X accelerometer Who Am i"
	lsm6dsv16x_read_whoami

	echo ">>>Testing LSM6DSV16X accelerometer data read"
	lsm6dsv16x_config
	sleep 0.01
	accel_data=$(lsm6dsv16x_read_accel)

	set -- $accel_data
	xval=$1  yval=$2  zval=$3

	printf "Acceleration [mg]  X=%d  Y=%d  Z=%d\n" "$xval" "$yval" "$zval"
fi

if [ "$1" = "stream" ]; then
	lsm6dsv16x_config              # put sensor in 120 Hz HP mode
	show_accel_bars "${2:-5}"      # default 5 samples/s
	exit 0
fi
