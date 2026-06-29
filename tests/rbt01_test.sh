#!/bin/sh

##
##############################################################################
# @file   rbt01_test.sh
# @author SRA-SAIL, Noida
# @brief  Script for testing the hardware functionality of the X-STM32MP-RBT01
#       board mounted on STM32MP157F-DK2 Discovery kit.
# If using a different motherboard, please modify the script accordingly.
# @note ensure that following conditions are met before running the script:
#       1. X-STM32MP-RBT01 board is mounted on the STM32MP157F-DK2 board
#       2. Motors and power supply are connected to X-STM32MP-RBT01 board
#       2. Jumper J1 on the RBT01 board is set to position 1-2 (enable EEPROM)
#       3. Correct DTB is flashed on the MPU board (enable Timers, disable SAI2, enable I2C5)
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

switch_gpio="gpiochip5 11"
test_count=0
key=""


print_test_output() {
    # Parameters: Test number, Test Name, Result [optional: pass/fail]
    if [ $# -eq 2 ]; then
        echo "TEST #$1: $2 Test . . ." 
    fi

    if [ $# -eq 3 ]; then
        echo -n "TEST #$1: $2 TEST: "
        if [ "$3" = "pass" ]; then
            echo "PASS"
        else 
            echo "FAIL"
        fi
    fi
}


# EEPROM (U1) Test
echo
print_test_output 1 "EEPROM M24C32R"

i2cset -f -y 0 0x50 0x01 0x11 0xaa i
i2cset -f -y 0 0x50 0x01 0x11

if [ `i2cget -f -y 0 0x50` == 0xaa ]; then
        print_test_output 1 "EEPROM M24C32R" pass
        test_count=$((test_count+1))
else
        print_test_output 1 "EEPROM M24C32R" fail
fi

echo
print_test_output 2 "Pressure Sensor LPS22HH"
if [ `i2cget -f -y 1 0x5d 0x0f` == 0xb3 ]; then
        print_test_output 2 "Pressure Sensor LPS22HH" pass
        test_count=$((test_count+1))
else
        print_test_output 2 "Pressure Sensor LPS22HH" fail
fi

echo
print_test_output 3 "Magnetometer Sensor IIS2MDC"
if [ `i2cget -f -y 1 0x1e 0x4f` == 0x40 ]; then
        print_test_output 3 "Magnetometer Sensor IIS2MDC" pass
        test_count=$((test_count+1))
else
        print_test_output 3 "Magnetometer Sensor IIS2MDC" fail
fi

echo
print_test_output 4 "Inertial Module ISM330DHCX"
if [ `i2cget -f -y 1 0x6b 0x0f` == 0x6b ]; then
        print_test_output 4 "Inertial Module ISM330DHCX" pass
        test_count=$((test_count+1))
else
        print_test_output 4 "Inertial Module ISM330DHCX" fail
fi

echo
print_test_output 5 "Time of Flight sensor VL53L5CX"
i2cset -f -y 1 0x29 0x7f 0xff 0x00 i
i2cset -f -y 1 0x29 0x00 0x00
if [ `i2cget -f -y 1 0x29` == 0xf0 ]; then
        print_test_output 5 "Time of Flight sensor VL53L5CX" pass
        test_count=$((test_count+1))
else
        print_test_output 5 "Time of Flight sensor VL53L5CX" fail
fi     
echo
print_test_output 6 "User Led"

echo
python3 led_test.py



echo "How many LEDs were working?"
read name


echo $name

if [ $name == 5 ]; then
        print_test_output 6 "User Led test" pass
        test_count=$((test_count+1))
else
        echo
        print_test_output 6 "User Led test" Fail
        echo
fi
echo
print_test_output 7 "STSPIN948 Motor driver test"
python3 motor_test.py
echo "How many motors are working?"
read number

if [ $number == 4 ]; then
        print_test_output 7 "STSPIN948 Motor driver test" pass
        test_count=$((test_count+1))
else
        echo
        print_test_output 7 "STSPIN948 Motor driver test" Fail
        echo
fi


echo
echo "**************************************"
if [ $test_count == 7 ]; then
        echo
        echo "VERDICT: BOARD OK"
        echo
else
        echo
        echo "VERDICT: BOARD FAILED"
        echo
fi
echo
echo "**************************************"

