#!/usr/bin/python3

##
##############################################################################
# @file   sensor_reader.py
# @author SRA-SAIL, Noida
# @brief  his script reads the data from various sources
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

import math
import os
import time
import subprocess
import 

import utils

data_file_path = "data/dump.txt"
data_file_lines = 0
data_file_line_current: int = 0

# Reads accelerometer value from IIO and return Euler angle


def euler_from_iio_accelerometer():
    accel = ism330dhcx.accelerometer_read()
    x = accel[0]
    y = accel[1]
    z = accel[2]

    roll = math.atan2(y, z)
    pitch = math.atan2(-x, math.sqrt(y * y + z * z))
    yaw = 0.0

    retVal = {"pitch": pitch, "roll": roll, "yaw": yaw}

    return retVal


# Parse a string from the generic buffer output
# q(-0.012125,0.002383,0.012325,0.999848), gb(0.000000,0.000000,0.000000), a(0.023904,0.005488,0.990787), g(3.885858,-2.380526,-0.700155)
def quaternion_from_gbuf_line(line):
    line = line.strip()

    if line.startswith("q("):
        split_line = line[2:].split(",")
        w = float(split_line[0].strip())
        x = float(split_line[1].strip())
        y = float(split_line[2].strip())

        z_string = split_line[3].replace(")", " ").strip()
        z = float(z_string)

        quaternion = {"w": w, "x": x, "y": y, "z": z}
        print(f"w = {w}, x = {x}, y = {y}, z = {z}")
        retVal = quaternion
    else:
        retVal = None

    return retVal


# Parse a string from the generic buffer output
# q(-0.012125,0.002383,0.012325,0.999848), gb(0.000000,0.000000,0.000000), a(0.023904,0.005488,0.990787), g(3.885858,-2.380526,-0.700155)


def euler_from_gbuf_line(line):
    line = line.strip()

    quaternion = quaternion_from_gbuf_line(line)

    if quaternion:
        retVal = utils.quaternion_to_euler(quaternion)
    else:
        retVal = None

    return retVal


def euler_from_file():
    global data_file_lines
    global data_file_line_current

    if data_file_lines == 0:
        script_path = os.path.abspath(__name__)
        script_dir = os.path.split(script_path)[0]
        abs_file_path = os.path.join(script_dir, data_file_path)
        file1 = open(abs_file_path, "r")
        data_file_lines = file1.readlines()[8:]
        file1.close()
        data_file_line_current = 0

    retVal = euler_from_gbuf_line(data_file_lines[data_file_line_current])
    data_file_line_current = (data_file_line_current + 1) % len(data_file_lines)
    return retVal


def test():
    for counter in range(300):
        val = euler_from_file()
        if val:
            print(f'Yaw = {val["yaw"]}, Pitch = {val["pitch"]}, Roll = {val["roll"]}')
        else:
            print("Other line")


if __name__ == "__main__":
    test()
