#!/usr/bin/python3

##
##############################################################################
# @file   line_reader.py
# @author SRA-SAIL, Noida
# @brief  This script reads the data from sensor data dump file,
#     used for testing
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
from subprocess import Popen, PIPE, CalledProcessError
import sys


TEST_DATA_FILE_PATH = "data/dump.txt"

data_file_lines = 0
data_file_line_current: int = 0


def file_getline():
    global data_file_lines
    global data_file_line_current

    if data_file_lines == 0:
        script_path = os.path.abspath(__name__)
        script_dir = os.path.split(script_path)[0]
        abs_file_path = os.path.join(script_dir, TEST_DATA_FILE_PATH)
        file1 = open(abs_file_path, "r")
        data_file_lines = file1.readlines()[8:]
        file1.close()
        data_file_line_current = 0

    while True:
        print(data_file_lines[data_file_line_current])
        data_file_line_current = (data_file_line_current + 1) % len(data_file_lines)
        time.sleep(0.05)
    return


def genbuffer_readfiles():
    # set_sample_result = subprocess.run(["echo", "104 > /sys/bus/iio/devices/iio\:device6/sampling_frequency"])
    with Popen(
        [
            "stdbuf",
            "-oL",
            "./iio_test_sensors",
            "-x",
            "20",
            "-a",
            "-c",
            "-1",
            "-o",
            "80",
            "-g",
            "0",
            "ism330dhcx_accel",
            "ism330dhcx_gyro",
            "lsm303ah_magn",
        ],
        stdout=PIPE,
        stderr=PIPE,
        bufsize=1,
        universal_newlines=True,
    ) as gen_buffer:
        for line in gen_buffer.stdout:
            print(line, end="")
            sys.stdout.flush()


if __name__ == "__main__":
    genbuffer_readfiles()

# ./bin/iio_test_sensors -x 20 -a -c -1 -o 80 -g 0  ism330dhcx_accel ism330dhcx_gyro lsm303ah_magn
