#!/usr/bin/python3

##
##############################################################################
# @file   iis2mdc.py
# @author SRA-SAIL, Noida
# @brief  Module for reading magnetic field data (PN = IIS2MDC) through IIO
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


class iis2mdc:
    def __init__(self, enumerator):
        self.enumerator = enumerator
        
        self.SSR_MAGN_NAME = "iis2mdc_magn"
        self.SSR_MAGN_VAL_PREFIX = "in_magn"

        self.magn_scale = None


    def magn_read(self):

        if self.magn_scale is None:
            self.magn_get_scale()

        x_value_prop_name = self.SSR_MAGN_VAL_PREFIX + "_x_raw"
        y_value_prop_name = self.SSR_MAGN_VAL_PREFIX + "_y_raw"
        z_value_prop_name = self.SSR_MAGN_VAL_PREFIX + "_z_raw"

        xraw = float(self.enumerator.read_sensor_property(self.SSR_MAGN_NAME, x_value_prop_name))
        yraw = float(self.enumerator.read_sensor_property(self.SSR_MAGN_NAME, y_value_prop_name))
        zraw = float(self.enumerator.read_sensor_property(self.SSR_MAGN_NAME, z_value_prop_name))

        magn_x = xraw * self.magn_scale[0]
        magn_y = yraw * self.magn_scale[1]
        magn_z = zraw * self.magn_scale[2]

        return [magn_x, magn_y, magn_z]
    

    def magn_get_sampling_freq(self):

        sampling_freq_prop_name = 'sampling_frequency'
        return float(self.enumerator.read_sensor_property(self.SSR_MAGN_NAME, sampling_freq_prop_name))


    def magn_set_sampling_freq(self, val):

        sampling_freq_prop_name = 'sampling_frequency'
        self.enumerator.write_sensor_property(self.SSR_MAGN_NAME, sampling_freq_prop_name, val)


    def magn_get_available_sampling_freq(self):

        sampling_freq_prop_name = 'sampling_frequency_available'
        prop_string = self.enumerator.read_sensor_property(self.SSR_MAGN_NAME, sampling_freq_prop_name)
        return [float(item) for item in prop_string.split()]

    def magn_get_scale(self):

        x_scale_prop_name = self.SSR_MAGN_VAL_PREFIX + '_x_scale'
        y_scale_prop_name = self.SSR_MAGN_VAL_PREFIX + '_y_scale'
        z_scale_prop_name = self.SSR_MAGN_VAL_PREFIX + '_z_scale'

        xscale = float(self.enumerator.read_sensor_property(self.SSR_MAGN_NAME, x_scale_prop_name))
        yscale = float(self.enumerator.read_sensor_property(self.SSR_MAGN_NAME, y_scale_prop_name))
        zscale = float(self.enumerator.read_sensor_property(self.SSR_MAGN_NAME, z_scale_prop_name))

        self.magn_scale = [xscale, yscale, zscale]
        return self.magn_scale


# Module Test
if __name__ == "__main__":

    enumerator = SensorEnumerator()
    enumerator.enumerate_iio_devices_by_name()

    iis2mdc = iis2mdc(enumerator)

    print("X-----Magnetometer-----X") 

    magn = iis2mdc.magn_read()
    print(f"Mag Field: X = {magn[0]}, Y = {magn[1]}, Z = {magn[2]}")

    current_sampling_frequency = iis2mdc.magn_get_sampling_freq()
    print(f"Current Sampling Frequency: {current_sampling_frequency}")

    available_sampling_frequency = iis2mdc.magn_get_available_sampling_freq()
    print(f"Available Sampling Frequency: {available_sampling_frequency}")

    current_scale = iis2mdc.magn_get_scale()
    print(f"Current Scale: X = {current_scale[0]}, Y = {current_scale[1]}, Z = {current_scale[2]}")
