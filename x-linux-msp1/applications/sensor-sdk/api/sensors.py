#!/usr/bin/python3

##
##############################################################################
# @file   sensor.py
# @author SRA-SAIL, Noida
# @brief  Modules implementing common sensor api functions
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


import os
import sensor_config as config

"""Class to store sensor details"""
class SensorDetails:
    def __init__(self, name, dts_node_name, sysfs_path):
        self.name = name
        self.dts_node_name = dts_node_name
        self.sysfs_path = sysfs_path
    def __str__(self):
        return f"Name = {self.name}, DTS Node Name = {self.dts_node_name}"
    def __repr__(self):
        return f"Name = {self.name}, DTS Node Name = {self.dts_node_name}, SysFs Path = {self.sysfs_path}"


class SensorEnumerator:

    def __init__(self):

        self.SSRNAME_ISM330DHCX_ACCEL = 'ism330dhcx_accel'
        self.SSRNAME_ISM330DHCX_GYRO = 'ism330dhcx_gyro'
        self.SSRNAME_IIS2MDC_MAGN = 'iis2mdc_magn'
        self.SSRNAME_IIS2DLPC_ACCEL = 'lis2dw12_accel'
        self.SSRNAME_STTS22H_TEMP = 'stts22h'
        self.SSRNAME_LPS22HH_PRES = 'lps22hh'

        self.SSRADDR_VD6283TX_ALS = 0x20
        self.SSRADDR_VL53L5CX_TOF = 0x29
        
        self.IIO_DEV_PATH = '/sys/bus/iio/devices'

        self.sensor_dictionary = {}


    # Enumerate all IIO devices, and store in a dictionary by name
    def enumerate_iio_devices_by_name(self):

        try:
            for filefolder in os.listdir(self.IIO_DEV_PATH):
                sensor_sysfs_path = os.path.join(self.IIO_DEV_PATH, filefolder)
                sensor_name_file = os.path.join(sensor_sysfs_path, 'name')
                sensor_uevent_file = os.path.join(sensor_sysfs_path, 'uevent')
                sensor_name = ''
                sensor_dtsnode_name = ''
                if not os.path.isdir(sensor_sysfs_path):
                    continue
                with open(sensor_name_file, 'r') as f:
                    sensor_name = f.readline().strip()
                if os.path.exists(sensor_uevent_file):
                    with open(sensor_uevent_file) as f:
                        for line in f:
                            if line.strip().startswith('OF_NAME'):
                                sensor_dtsnode_name = line.strip().split('=')[1].strip()
                                self.sensor_dictionary[sensor_name] = SensorDetails(sensor_name, sensor_dtsnode_name, sensor_sysfs_path)
                                break
        except OSError:
            pass
        except Exception as exc:
            pass


    def print_enumerated_iio_devices(self):

        for key, value in self.sensor_dictionary.items():
            print(key, value)

    def find_iio_device_by_dtnode_name(self, data, name):
            """Find a IIO devices by device tree node name, 
            and return the sysfs path"""
            prefix = "/sys/bus/iio/devices"
            of_name = "OF_NAME=" + name
            try:
                for filefolder in os.listdir(prefix):
                    with open(prefix + "/" + filefolder + "/uevent") as f:
                        for line in f:
                            if line.split("\n")[0] == of_name:
                                """return directory which contains "data" """
                                if os.path.exists(prefix + "/" + filefolder + "/" + data):
                                    return prefix + "/" + filefolder + "/"
            except OSError:
                pass
            except Exception as exc:
                pass
            return None

    # Test if a sensor name exists in the dictionary
    def does_sensor_exist(self, sensor_name):

        return sensor_name in self.sensor_dictionary

    def read_sensor_property(self, sensor_name, prop_name):
        sensor_sysfs_path = self.sensor_dictionary[sensor_name].sysfs_path
        sensor_field_sysfs_path = os.path.join(sensor_sysfs_path, prop_name)
        try:
            with open(sensor_field_sysfs_path, "r") as f:
                return f.read().strip()
        except Exception as exc:
            print(f"[ERROR] read {sensor_sysfs_path}{prop_name}", exc)
            return None
        
    def write_sensor_property(self, sensor_name, prop_name, prop_value):
        sensor_sysfs_path = self.sensor_dictionary[sensor_name].sysfs_path
        sensor_field_sysfs_path = os.path.join(sensor_sysfs_path, prop_name)
        try:
            with open(sensor_field_sysfs_path, "w") as f:
                return f.write(str(prop_value))
        except Exception as exc:
            print(f"[ERROR] write {sensor_sysfs_path}{prop_name}", exc)
            return None
        
    def get_sensors(self):
        return self.sensor_dictionary
        

# Module Test
if __name__ == "__main__":

    sensors = SensorEnumerator()
    sensors.enumerate_iio_devices_by_name()
    sensors.print_enumerated_iio_devices()