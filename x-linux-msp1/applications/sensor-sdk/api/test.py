#!/usr/bin/python3

##
##############################################################################
# @file   test.py
# @author SRA-SAIL, Noida
# @brief  Module for Industrial Accelerometer (PN = IIS2DLPC) through IIO
##############################################################################
# @attention
#
# Copyright (c) 2024 STMicroelectronics.
# All rights reserved.
#
# This software is licensed under terms that can be found in the LICENSE file
# in the root directory of this software component.
# If no LICENSE file comes with this software, it is provided AS-IS.
#
##############################################################################
##

from sensors import SensorEnumerator
import iis2dlpc
import ism330dhcx
import lps22hh
import stts22h

# Module Test
if __name__ == "__main__":

    enumerator = SensorEnumerator()
    enumerator.enumerate_iio_devices_by_name()

    iis2dlpc = iis2dlpc.iis2dlpc(enumerator)

    iis2dlpc.accel_set_sampling_freq(25)

    print("X-----Accelerometer-----X") 

    accel = iis2dlpc.accel_read()
    print(f"Acceleration: X = {accel[0]}, Y = {accel[1]}, Z = {accel[2]}")

    current_sampling_frequency = iis2dlpc.accel_get_sampling_freq()
    print(f"Current Sampling Frequency: {current_sampling_frequency}")

    available_sampling_frequency = iis2dlpc.accel_get_available_sampling_freq()
    print(f"Available Sampling Frequency: {available_sampling_frequency}")

    current_scale = iis2dlpc.accel_get_scale()
    print(f"Current Scale: X = {current_scale[0]}, Y = {current_scale[1]}, Z = {current_scale[2]}")

    available_scales = iis2dlpc.accel_get_available_scale()
    print(f"Available Scales: {available_scales}")

    ism330dhcx = ism330dhcx.ism330dhcx(enumerator)

    ism330dhcx.accel_set_sampling_freq(52.0)
    ism330dhcx.gyro_set_sampling_freq(52.0)

    print("X-----Accelerometer-----X") 

    accel = ism330dhcx.accel_read()
    print(f"Acceleration: X = {accel[0]}, Y = {accel[1]}, Z = {accel[2]}")

    current_sampling_frequency = ism330dhcx.accel_get_sampling_freq()
    print(f"Current Sampling Frequency: {current_sampling_frequency}")

    available_sampling_frequency = ism330dhcx.accel_get_available_sampling_freq()
    print(f"Available Sampling Frequency: {available_sampling_frequency}")

    current_scale = ism330dhcx.accel_get_scale()
    print(f"Current Scale: X = {current_scale[0]}, Y = {current_scale[1]}, Z = {current_scale[2]}")

    available_scales = ism330dhcx.accel_get_available_scale()
    print(f"Available Scales: {available_scales}")


    print("X-----Gyroscope-----X") 

    ang_vel = ism330dhcx.gyro_read()
    print(f"Angular Velocity: X = {ang_vel[0]}, Y = {ang_vel[1]}, Z = {ang_vel[2]}")

    current_sampling_frequency = ism330dhcx.gyro_get_sampling_freq()
    print(f"Current Sampling Frequency: {current_sampling_frequency}")

    available_sampling_frequency = ism330dhcx.gyro_get_available_sampling_freq()
    print(f"Available Sampling Frequency: {available_sampling_frequency}")

    current_scale = ism330dhcx.gyro_get_scale()
    print(f"Current Scale: X = {current_scale[0]}, Y = {current_scale[1]}, Z = {current_scale[2]}")

    available_scales = ism330dhcx.gyro_get_available_scale()
    print(f"Available Scales: {available_scales}")

    lps22hh = lps22hh.lps22hh(enumerator)

    lps22hh.pres_set_sampling_freq(10)

    print("X-----Pressure-----X") 

    temp = lps22hh.pres_read()
    print(f"Temperature: T = {temp}")

    current_sampling_frequency = lps22hh.pres_get_sampling_freq()
    print(f"Current Sampling Frequency: {current_sampling_frequency}")

    available_sampling_frequency = lps22hh.pres_get_available_sampling_freq()
    print(f"Available Sampling Frequency: {available_sampling_frequency}")

    current_scale = lps22hh.pres_get_scale()
    print(f"Current Scale: {current_scale}")

    stts22h = stts22h.stts22h(enumerator)

    print("X-----Temperature-----X") 

    temp = stts22h.temp_read()
    print(f"Temperature: T = {temp}")

    current_sampling_frequency = stts22h.temp_get_sampling_freq()
    print(f"Current Sampling Frequency: {current_sampling_frequency}")

    available_sampling_frequency = stts22h.temp_get_available_sampling_freq()
    print(f"Available Sampling Frequency: {available_sampling_frequency}")

    current_scale = stts22h.temp_get_scale()
    print(f"Current Scale: {current_scale}")

    print("--->> Sensor Test Completed : PASS <<---")