#!/bin/sh

##
##############################################################################
# @file   board_utils.sh
# @author SRA-SAIL, Noida
# @brief  Helper Script for testing the hardware functionality of the X-STM32MP
#       boards. Common variables and methods are defined here.
# Please modify the script as per the board(s) used.
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

TEST_HOST_BOARD="stm32mp257f-dk"
TEST_EXPANSION_BOARD="X-STM32MP-EVG01"
I2C_BUS_ID_EEPROM=0
I2C_BUS_PRIMARY=1

# 7-bit addresses of the devices
DEVICE_ADDR_M24C32=0x50
DEVICE_ADDR_STSAFE_A110=0x20
DEVICE_ADDR_ST25R3916B=0x50
DEVICE_ADDR_M24M01=0x56
DEVICE_ADDR_LED1202_LOCAL=0x5A
DEVICE_ADDR_LED1202_GLOBAL=0x5C
DEVICE_ADDR_LSM6DV16X=0x6B              # SA0=1 → 0x6B   (SA0=0 → 0x6A)

USER_SWITCH_GPIO=PD7
GPIO_LED1=PG2
GPIO_LED2=PH11
GPIO_LED3=PD13
GPIO_LED4=PC7



INFO_LEVEL="error" # Supported values: error/debug/silent

UTILS_BANNER_WIDTH=60

# Error messages are supressed if INFO LEVEL is set to "silent"
utils_print_error() {
	if [ "$INFO_LEVEL" = "error" ] || [ "$INFO_LEVEL" = "debug" ]; then
		printf "ERROR: %s\n" "$*" >&2
	fi
}

utils_print_debug() {
	if [ "$INFO_LEVEL" = "debug" ]; then
		printf "DEBUG: %s\n" "$*" >&1
	fi
}

utils_exit_on_error() {
	if [ "$INFO_LEVEL" = "error" ] || [ "$INFO_LEVEL" = "debug" ]; then
		printf "ERROR: %s\n" "$*" >&2
	fi
	exit 1
}

utils_check_install() {
	command -v "$1" >/dev/null 2>&1
	if [ "$?" -ne 0 ]; then

		utils_print_error "$1" "not found, install it."
		return 1
	fi

	return 0
}

#-- Check if the board is STM32MP157F-DK2 ---------------------------------- #
utils_check_board() {
	if [ -z "$1" ]; then
		utils_print_error " [utils_check_board]- missing name input."
		return 1
	fi

	board_name="$1"
	local compat=$(tr '\0' '\n' < /proc/device-tree/compatible)

	case "$compat" in
		*"${board_name}"*)
			:
			;;
		*)
			return 1
			;;
	esac
	return 0
}

utils_print_center_message() {
	local line_width="$1"
	local pad_char="$2"
	local message="$3"
	
	if [ -z "$message" ]; then
		echo "$(printf "%*s" "$line_width" " " | tr " " "$pad_char")"
	else
		local message_length=${#message}
		local star_count=$(( (line_width-message_length-2) / 2 ))
		if [ "$star_count" -lt 0 ]; then
			star_count=0
		fi

		local padding=$(printf "%*s" "$star_count" " " | tr " " "$pad_char")
		printf "%s %s %s\n" "$padding" "$message" "$padding"
	fi
}

utils_print_testbanner() {
	current_test_number=$1
	current_test_name=$2

	local message=$(printf 'TEST #%02d: %s Test' "$current_test_number" "$current_test_name")
	printf "\n"
	utils_print_center_message "$UTILS_BANNER_WIDTH" "*" "$message"
	#_utils_print_center_message "$UTILS_BANNER_WIDTH" "*"
}

utils_print_testresult() {
	if [ "$1" = "pass" ]; then

		utils_print_center_message "$UTILS_BANNER_WIDTH" "=" "TEST PASSED"
	else 
		utils_print_center_message "$UTILS_BANNER_WIDTH" "=" "TEST FAILED"
	fi

	echo
}

utils_hex2dec() {
	h=${1#0x}; h=${h#0X}          # strip 0x/0X
	printf '%d' "0x$h"            # POSIX printf understands C integer syntax
}

#  Usage :  utils_i2c_write  <bus_id> <dev_addr> <remaining args passed verbatim>
utils_i2c_write() {
	[ $# -lt 3 ] && {
		utils_print_error '[utils_i2c_write] - need at least BUS, ADDR and one DATA/REG byte'
		return 1
	}

	local bus=$1 addr=$2; shift 2

	utils_check_install i2cset
	utils_print_debug "i2cset -y $bus $addr $@"
	if ! i2cset -y "$bus" "$addr" "$@"; then
		printf 'ERROR: i2cset failed (bus=%s, addr=%s, args=%s)\n' \
			   "$bus" "$addr" "$*" >&2
		return 1
	fi

	# Small delay might be needed
	# sleep 0.01

	return 0
}

utils_i2c_read_byte() {
	[ $# -lt 1 ] && {
		utils_print_error '[utils_i2c_read_byte] - need register address'
		exit 1
	}
	local I2C_BUS=$1
	local DEVICE_ADDR=$2
	local reg=$3
	val=$(i2cget -y "$I2C_BUS" "$DEVICE_ADDR" "$reg" 2>/dev/null)
	utils_hex2dec "$val"
}

utils_unit_test() {

	echo ">>>Testing utils_print_error"
	utils_print_error "This is a test error message"

	echo ">>>Testing utils_print_debug"
	utils_print_debug "This is a test debug message"

	echo ">>>Testing utils_check_install"
	utils_check_install i2cget

	echo ">>>Testing utils_check_install with non-existing command"
	utils_check_install non_existing_command

	echo ">>>Testing utils_check_board"
	utils_check_board "$TEST_HOST_BOARD"
	if [ $? -ne 0 ]; then
		echo "Error: This script is intended to be run on the STM32MP157F-DK2 board."
		exit 1
	else 
		echo -n "Board detected: "
		echo "$board_name" | tr '[:lower:]' '[:upper:]'
	fi

	echo ">>>Testing print_test_output"
	utils_print_testbanner 1 "EEPROM M24C32(U1)"
	utils_print_testresult pass

	echo ">>>Testing utils_hex2dec"
	hex_value="0x1A"
	dec_value=$(utils_hex2dec "$hex_value")
	echo "Hex value: $hex_value, Decimal value: $dec_value"

	echo ">>>Testing utils_i2c_write"
	utils_i2c_write 0 0x50 0x01 0x11 0xaa i
	if [ $? -ne 0 ]; then
		echo "Error: utils_i2c_write failed."
		exit 1
	fi
}

if [ "$1" = "test" ]; then
	utils_unit_test
fi
