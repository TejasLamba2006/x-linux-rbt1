#!/usr/bin/python3

##
##############################################################################
# @file   sensor_config.py
# @author SRA-SAIL, Noida
# @brief  This script comntains configuration and related data types
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

import enum


class SensorDataSource(enum.Enum):
    simulate = 1
    static_file = 2
    sense_hat = 3
    MSP01 = 4


data_source = SensorDataSource.MSP01

WS_PORT = 7890
