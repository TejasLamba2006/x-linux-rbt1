#!/usr/bin/python3

##
##############################################################################
# @file   stts22h.py
# @author SRA-SAIL, Noida
# @brief  Module for reading Temperature Sensor (PN = STTS22H) through IIO
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

class stts22h:

    def __init__(self, enumerator):
        self.enumerator = enumerator
        self.SSR_TEMP_NAME = "stts22h"
        self.SSR_TEMP_VAL_PREFIX = "in_temp_ambient"

        self.temp_scale = None

    def temp_read(self):
            
            if self.temp_scale is None:
                self.temp_get_scale()

            value_prop_name = self.SSR_TEMP_VAL_PREFIX + "_raw"
            val_raw = float(self.enumerator.read_sensor_property(self.SSR_TEMP_NAME, value_prop_name))
            self.temp_scale = 0.01 # 0.01 for linux v6.1
            return self.temp_scale * val_raw


    def temp_get_sampling_freq(self):

        sampling_freq_prop_name = 'sampling_frequency'
        return float(self.enumerator.read_sensor_property(self.SSR_TEMP_NAME, sampling_freq_prop_name))
    

    def temp_set_sampling_freq(self, val):
            
        sampling_freq_prop_name = 'sampling_frequency'
        self.enumerator.write_sensor_property(self.SSR_TEMP_NAME, sampling_freq_prop_name, val)


    def temp_get_available_sampling_freq(self):
            
            sampling_freq_prop_name = 'sampling_frequency_available'
            prop_string = self.enumerator.read_sensor_property(self.SSR_TEMP_NAME, sampling_freq_prop_name)
            return [float(item) for item in prop_string.split()]


    def temp_get_scale(self):

        scale_prop_name = self.SSR_TEMP_VAL_PREFIX + '_scale'
        self.temp_scale = float(self.enumerator.read_sensor_property(self.SSR_TEMP_NAME, scale_prop_name))
        return self.temp_scale

# Module Test
if __name__ == "__main__":

    enumerator = SensorEnumerator()
    enumerator.enumerate_iio_devices_by_name()

    stts22h = stts22h(enumerator)

    print("X-----Temperature-----X") 

    temp = stts22h.temp_read()
    print(f"Temperature: T = {temp}")

    current_sampling_frequency = stts22h.temp_get_sampling_freq()
    print(f"Current Sampling Frequency: {current_sampling_frequency}")

    available_sampling_frequency = stts22h.temp_get_available_sampling_freq()
    print(f"Available Sampling Frequency: {available_sampling_frequency}")

    current_scale = stts22h.temp_get_scale()
    print(f"Current Scale: {current_scale}")
