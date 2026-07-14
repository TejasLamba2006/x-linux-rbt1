#!/usr/bin/python3

##
##############################################################################
# @file   lps22hh.py
# @author SRA-SAIL, Noida
# @brief  Module for reading Pressure Sensor (PN = LPS22HH) through IIO
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

class lps22hh:

    def __init__(self, enumerator):
        self.enumerator = enumerator
        self.SSR_PRES_NAME = "lps22hh"
        self.SSR_PRES_VAL_PREFIX = "in_pressure"

        self.pres_scale = None

    def pres_read(self):
            
        if self.pres_scale is None:
            self.pres_get_scale()

        value_prop_name = self.SSR_PRES_VAL_PREFIX + "_raw"
        val_raw = float(self.enumerator.read_sensor_property(self.SSR_PRES_NAME, value_prop_name))
        return int(self.pres_scale * val_raw/4)


    def pres_get_sampling_freq(self):

        sampling_freq_prop_name = 'sampling_frequency'
        return float(self.enumerator.read_sensor_property(self.SSR_PRES_NAME, sampling_freq_prop_name))
    

    def pres_set_sampling_freq(self, val):
            
        sampling_freq_prop_name = 'sampling_frequency'
        self.enumerator.write_sensor_property(self.SSR_PRES_NAME, sampling_freq_prop_name, val)


    def pres_get_available_sampling_freq(self):
            
        sampling_freq_prop_name = 'sampling_frequency_available'
        prop_string = self.enumerator.read_sensor_property(self.SSR_PRES_NAME, sampling_freq_prop_name)
        return [float(item) for item in prop_string.split()]


    def pres_get_scale(self):

        scale_prop_name = self.SSR_PRES_VAL_PREFIX + '_scale'
        self.pres_scale = float(self.enumerator.read_sensor_property(self.SSR_PRES_NAME, scale_prop_name))
        return self.pres_scale

# Module Test
if __name__ == "__main__":

    enumerator = SensorEnumerator()
    enumerator.enumerate_iio_devices_by_name()

    lps22hh = lps22hh(enumerator)

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
