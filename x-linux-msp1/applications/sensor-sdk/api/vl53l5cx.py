#!/usr/bin/python3

##
##############################################################################
# @file   vl53l5cx.py
# @author SRA-SAIL, Noida
# @brief  Python wrapper for reading ToF data (PN = VL53L5CX)
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

DEBUG = False
BINARY_PATH = "../../binaries/tof"


class vl53l5cx:
    def __init__(self):
        pass

    def get_distance(self):
        process = subprocess.Popen(
            [BINARY_PATH, "1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("distance:", result)

        return result

    def set_resolution(self):
        process = subprocess.Popen(
            [BINARY_PATH, "2"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)

        return result

    def get_resolution(self):
        process = subprocess.Popen(
            [BINARY_PATH, "3"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)

        return result

    def set_ranging_frequency(self):
        process = subprocess.Popen(
            [BINARY_PATH, "4"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)
        return result

    def get_ranging_frequency(self):
        process = subprocess.Popen(
            [BINARY_PATH, "5"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)

        return result

    def set_target(self):
        process = subprocess.Popen(
            [BINARY_PATH, "6"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)

        return result

    def get_target(self):
        process = subprocess.Popen(
            [BINARY_PATH, "7"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)

        return result

    def set_integration_time_ms(self):
        process = subprocess.Popen(
            [BINARY_PATH, "8"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)

        return result

    def get_integration_time_ms(self):
        process = subprocess.Popen(
            [BINARY_PATH, "9"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)

        return result

    def set_power_down(self):
        process = subprocess.Popen(
            [BINARY_PATH, "10"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)

        return result

    def get_power_down(self):
        process = subprocess.Popen(
            [BINARY_PATH, "11"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)

        return result

    def set_parameters(self):
        process = subprocess.Popen(
            [BINARY_PATH, "14"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        if DEBUG:
            print(txt)
        result = []
        for word in txt.split():
            if DEBUG:
                print("word:", word)
            if word.isdigit():
                result.append(int(word))
                if DEBUG:
                    print("numbers:", result)

        return result


# Test Main
if __name__ == "__main__":
    if DEBUG:
        tof = vl53l5cx()

        # distance= tof.get_distance()
        # resolution = tof.get_resolution()

    # set_resolution=tof_set_resolution()
    # get_resolution=tof_get_resolution()
    # set_target=tof_set_target()
    # get_target=tof_get_target()
    # set_integration_time=tof_set_integration_time_ms()
    # get_integration_time=tof_get_integration_time_ms()
    # set_power_mode=tof_set_power_down()
    # get_power_mode=tof_get_power_down()
    # set_params=tof_set_parameters()

    # print("distance=",distance[0])

    # if(debug1):
    #         print("set_resolution=",set_resolution[0])
    #         print("get_resolution=",get_resolution[0])
    #         print("set_ranging=",set_ranging[0])
    #         print("get_ranging=",get_ranging[0])
    #         print("set_target=",set_target[0])
    #         print("get_target=",get_target[0])
    #         print("set_integration_time=",set_integration_time[0])
    #         print("get_integration_time=",get_integration_time[0])
    #         print("set_power_mode=",set_power_mode[0])
    #         print("get_power_mode=",get_power_mode[0])
    #         #print("set_ranging_mode=",set_ranging_mode[0])
    #         #print("get_ranging_mode=",get_ranging_mode[0])
    #         print("set_params")
