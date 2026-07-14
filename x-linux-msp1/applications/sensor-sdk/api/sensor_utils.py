#!/usr/bin/python3

##
##############################################################################
# @file   sensor_utils.py
# @author SRA-SAIL, Noida
# @brief  This file contains common utility functions used in
# this application
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
import socket

SIMULATE = 0

# Convert Euler angle to quaternion


def euler_to_quaternion(angle):
    yaw = angle["yaw"]
    pitch = angle["pitch"]
    roll = angle["roll"]

    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)

    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    y = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy

    retVal = {"w": w, "x": x, "y": y, "z": z}

    return retVal


# Convert quaternion to Euler angle, to check


def quaternion_to_euler(angle):
    # roll (x-axis rotation)
    sinr_cosp = 2 * (angle["w"] * angle["x"] + angle["y"] * angle["z"])
    cosr_cosp = 1 - 2 * angle["x"] * angle["x"] + angle["y"] * angle["y"]
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # pitch (y-axis rotation)
    sinp = 2 * (angle["w"] * angle["y"] - angle["z"] * angle["x"])
    if abs(sinp) >= 1:
        # use 90 degrees if value of range
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)

    # yaw (z-axis rotation)
    siny_cosp = 2 * angle["w"] * angle["z"] + angle["x"] * angle["y"]
    cosy_cosp = 1 - 2 * angle["y"] * angle["y"] + angle["z"] * angle["z"]
    yaw = math.atan2(siny_cosp, cosy_cosp)

    retVal = {"pitch": pitch, "roll": roll, "yaw": yaw}

    return retVal


def get_ipaddress():
    conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    conn.settimeout(0)
    try:
        # need not be reachable
        conn.connect(("10.254.254.254", 1))
        ip = conn.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        conn.close()
    return ip


def read_board_compatibility_name():
    if SIMULATE > 0:
        return "all"
    else:
        try:
            with open("/proc/device-tree/compatible") as fp:
                string = fp.read()
                return string.split(",")[-1].rstrip("\x00")
        except:
            return "all"


if __name__ == "__main__":
    print("IP Address = ", get_ipaddress())
    print("Board Name = ", read_board_compatibility_name())
