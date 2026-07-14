#!/usr/bin/python3

##
##############################################################################
# @file   ism330dhcx.py
# @author SRA-SAIL, Noida
# @brief  Module for reading Inertial Sensor (PN = ISM330DHCX) through IIO
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

class ism330dhcx:

    def __init__(self, enumerator):
            self.enumerator = enumerator

            self.SSR_ACCEL_NAME = 'ism330dhcx_accel'
            self.SSR_ACCEL_VAL_PREFIX = 'in_accel'

            self.SSR_GYRO_NAME = 'ism330dhcx_gyro'
            self.SSR_GYRO_VAL_PREFIX = 'in_anglvel'

            self.accel_scale = None
            self.gyro_scale = None
           
    def accel_read(self):

        if self.accel_scale is None:
            self.accel_get_scale()

        x_value_prop_name = self.SSR_ACCEL_VAL_PREFIX + '_x_raw'
        y_value_prop_name = self.SSR_ACCEL_VAL_PREFIX + '_y_raw'
        z_value_prop_name = self.SSR_ACCEL_VAL_PREFIX + '_z_raw'

        xraw = float(self.enumerator.read_sensor_property(self.SSR_ACCEL_NAME, x_value_prop_name))
        yraw = float(self.enumerator.read_sensor_property(self.SSR_ACCEL_NAME, y_value_prop_name))
        zraw = float(self.enumerator.read_sensor_property(self.SSR_ACCEL_NAME, z_value_prop_name))

        accel_x = xraw * self.accel_scale[0]
        accel_y = yraw * self.accel_scale[1]
        accel_z = zraw * self.accel_scale[2]

        return [accel_x, accel_y, accel_z]


    def accel_get_sampling_freq(self):

        sampling_freq_prop_name = 'sampling_frequency'
        return float(self.enumerator.read_sensor_property(self.SSR_ACCEL_NAME, sampling_freq_prop_name))


    def accel_set_sampling_freq(self, val):

        sampling_freq_prop_name = 'sampling_frequency'
        self.enumerator.write_sensor_property(self.SSR_ACCEL_NAME, sampling_freq_prop_name, val)


    def accel_get_available_sampling_freq(self):

        sampling_freq_prop_name = 'sampling_frequency_available'
        prop_string = self.enumerator.read_sensor_property(self.SSR_ACCEL_NAME, sampling_freq_prop_name)
        return [float(item) for item in prop_string.split()]

    def accel_get_scale(self):

        x_scale_prop_name = self.SSR_ACCEL_VAL_PREFIX + '_x_scale'
        y_scale_prop_name = self.SSR_ACCEL_VAL_PREFIX + '_y_scale'
        z_scale_prop_name = self.SSR_ACCEL_VAL_PREFIX + '_z_scale'

        xscale = float(self.enumerator.read_sensor_property(self.SSR_ACCEL_NAME, x_scale_prop_name))
        yscale = float(self.enumerator.read_sensor_property(self.SSR_ACCEL_NAME, y_scale_prop_name))
        zscale = float(self.enumerator.read_sensor_property(self.SSR_ACCEL_NAME, z_scale_prop_name))

        self.accel_scale = [xscale, yscale, zscale]
        return self.accel_scale

    def accel_get_available_scale(self):

        scale_prop_name = self.SSR_ACCEL_VAL_PREFIX + '_scale_available'
        prop_string = self.enumerator.read_sensor_property(self.SSR_ACCEL_NAME, scale_prop_name)
        return [float(item) for item in prop_string.split()]


    # ------------------------------------------------------------------------------- #
    # All Functions for Gyroscope (IMU = ISM330DHCX)

    def gyro_read(self):

            if self.gyro_scale is None:
                self.gyro_get_scale()
        
            x_value_prop_name = self.SSR_GYRO_VAL_PREFIX + '_x_raw'
            y_value_prop_name = self.SSR_GYRO_VAL_PREFIX + '_y_raw'
            z_value_prop_name = self.SSR_GYRO_VAL_PREFIX + '_z_raw'
        
            xraw = float(self.enumerator.read_sensor_property(self.SSR_GYRO_NAME, x_value_prop_name))
            yraw = float(self.enumerator.read_sensor_property(self.SSR_GYRO_NAME, y_value_prop_name))
            zraw = float(self.enumerator.read_sensor_property(self.SSR_GYRO_NAME, z_value_prop_name))
        
            gyro_x = xraw * self.gyro_scale[0]
            gyro_y = yraw * self.gyro_scale[1]
            gyro_z = zraw * self.gyro_scale[2]
        
            return [gyro_x, gyro_y, gyro_z]

    def gyro_get_sampling_freq(self):
        
            sampling_freq_prop_name = 'sampling_frequency'
            return float(self.enumerator.read_sensor_property(self.SSR_GYRO_NAME, sampling_freq_prop_name))

    def gyro_set_sampling_freq(self, val):
        
            sampling_freq_prop_name = 'sampling_frequency'
            self.enumerator.write_sensor_property(self.SSR_GYRO_NAME, sampling_freq_prop_name, val)

    def gyro_get_available_sampling_freq(self):
            
                sampling_freq_prop_name = 'sampling_frequency_available'
                prop_string = self.enumerator.read_sensor_property(self.SSR_GYRO_NAME, sampling_freq_prop_name)
                return [float(item) for item in prop_string.split()]

    def gyro_get_scale(self):
            
            x_scale_prop_name = self.SSR_GYRO_VAL_PREFIX + '_x_scale'
            y_scale_prop_name = self.SSR_GYRO_VAL_PREFIX + '_y_scale'
            z_scale_prop_name = self.SSR_GYRO_VAL_PREFIX + '_z_scale'
        
            xscale = float(self.enumerator.read_sensor_property(self.SSR_GYRO_NAME, x_scale_prop_name))
            yscale = float(self.enumerator.read_sensor_property(self.SSR_GYRO_NAME, y_scale_prop_name))
            zscale = float(self.enumerator.read_sensor_property(self.SSR_GYRO_NAME, z_scale_prop_name))

            self.gyro_scale = [xscale, yscale, zscale]
            return self.gyro_scale

    def gyro_get_available_scale(self):
                
                    scale_prop_name = self.SSR_GYRO_VAL_PREFIX + '_scale_available'
                    prop_string = self.enumerator.read_sensor_property(self.SSR_GYRO_NAME, scale_prop_name)
                    return [float(item) for item in prop_string.split()]


# Module Test
if __name__ == "__main__":

    enumerator = SensorEnumerator()
    enumerator.enumerate_iio_devices_by_name()

    ism330dhcx = ism330dhcx(enumerator)

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



    