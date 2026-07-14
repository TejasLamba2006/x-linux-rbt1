#!/usr/bin/python3

##
##############################################################################
# @file   vd6283.py
# @author SRA-SAIL, Noida
# @brief  Module for reading ALS Data (PN = VD6283)
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

import subprocess

BINARY_PATH_VD6283_COLOR = "../../binaries/vd6283_color"

debug = False
lux_ret = 0


class vl53l5cx:
    def __init__(self):
        pass

    def color_sensor_read():
        process = subprocess.Popen(
            BINARY_PATH_VD6283_COLOR, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if debug:
            print(txt)
        numbers = []
        for word in txt.split():
            if debug:
                print("word:", word)
            if word.isdigit():
                numbers.append(int(word))
                if debug:
                    print("numbers:", numbers)

        return numbers

    def increase_exposure_time():
        process = subprocess.Popen(
            [BINARY_PATH_VD6283_COLOR, "6"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def decrease_exposure_time():
        process = subprocess.Popen(
            [BINARY_PATH_VD6283_COLOR, "4"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def increase_gain():
        process = subprocess.Popen(
            [BINARY_PATH_VD6283_COLOR, "8"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def decrease_gain():
        process = subprocess.Popen(
            [BINARY_PATH_VD6283_COLOR, "2"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def decrease_inter_measurement():
        process = subprocess.Popen(
            [BINARY_PATH_VD6283_COLOR, "1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def increase_inter_measurement():
        process = subprocess.Popen(
            [BINARY_PATH_VD6283_COLOR, "3"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def color_sensor_light():
        process = subprocess.Popen(
            BINARY_PATH_VD6283_COLOR, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # process = subprocess.Popen([BINARY_PATH_VD6283_COLOR, "0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        txt = process.stdout.read().decode("utf-8")
        if debug:
            print(txt)
        numbers = []
        for word in txt.split():
            if debug:
                print("word:", word)
            if word.isdigit():
                numbers.append(int(word))
                if debug:
                    print("numbers:", numbers)

        return numbers


# Module Test
if __name__ == "__main__":

    vl53l5cx = vl53l5cx()
    color_ret = vl53l5cx.color_sensor_light()
    print("color_ret=", color_ret)