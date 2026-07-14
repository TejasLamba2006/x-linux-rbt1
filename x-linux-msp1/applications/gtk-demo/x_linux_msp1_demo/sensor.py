#!/usr/bin/python3

##
##############################################################################
# @file   sensor.py
# @author SRA-SAIL, Noida
# @brief  Display the sensor data (as a Demo Application dialog)
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

from time import sleep, time
import os
import math
import random
import sensor_config as config
import cairo
from stts22h import stts22h
from gi.repository import GdkPixbuf
from gi.repository import GLib
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Gtk

import gi
import subprocess

gi.require_version("Gtk", "3.0")
# from  ism330dhcx import ism330dhcx


# time between each sensor mesearuement (1s)
TIME_UPATE = 6000


class Sensors:
    def __init__(self):
        """ """
        self.sensor_dictionnary = {}

    def found_iio_device_with_name(self, data, name):
        prefix = "/sys/bus/iio/devices/"
        of_name = "OF_NAME=" + name
        print(data)
        print(name)
        try:
            for filefolder in os.listdir(prefix):
                with open(prefix + "/" + filefolder + "/uevent") as f:
                    for line in f:
                        print(line)
                        if line.split("\n")[0] == of_name:
                            """return directory which contains "data" """
                            print(line)
                            if os.path.exists(prefix + "/" + filefolder + "/" + data):
                                return prefix + "/" + filefolder + "/"
                                break
        except OSError:
            pass
        except Exception as exc:
            pass
        return None

    def found_all_sensor_path(self):
        self.sensor_dictionnary["temperature"] = self.found_iio_device_with_name(
            "in_temp_ambient_raw", "stts22h_temp"
        )
        self.sensor_dictionnary["pressure"] = self.found_iio_device_with_name(
            "in_pressure_raw", "lps22hh"
        )
        # self.sensor_dictionnary['accelerometer'] = self.found_iio_device_with_name("in_accel_x_raw", "st_ism330dhcx")
        # self.sensor_dictionnary['gyroscope'] = self.found_iio_device_with_name("in_anglvel_x_raw", "st_ism330dhcx")
        # self.sensor_dictionnary['magnetometer'] = self.found_iio_device_with_name("in_magn_x_raw", "iis2mdc_magn")
        self.sensor_dictionnary["sec_accelerometer"] = self.found_iio_device_with_name(
            "in_accel_x_raw", "iis2dlpc"
        )

        print(
            "[DEBUG] temperature (STTS22H)   -> ",
            self.sensor_dictionnary["temperature"],
            "<",
        )
        print(
            "[DEBUG] pressure (LPS22H)  -> ", self.sensor_dictionnary["pressure"], "<"
        )
        # print("[DEBUG] accelerometer (ISM330DHCX) -> ", self.sensor_dictionnary['accelerometer'], "<")
        # print("[DEBUG] gyroscope  (ISM330DHCX)   -> ", self.sensor_dictionnary['gyroscope'], "<")
        # print("[DEBUG] magnetometer  (IIS2MDC)   -> ", self.sensor_dictionnary['magnetometer'], "<")
        print(
            "[DEBUG] sec_accelerometer (IIS2DLPC)     -> ",
            self.sensor_dictionnary["sec_accelerometer"],
            "<",
        )

    def temperature_read(self):
        prefix_path = self.sensor_dictionnary["temperature"]
        try:
            with open(prefix_path + "in_temp_ambient_" + "raw", "r") as f:
                raw = float(f.read()) / 100.0
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_temp_ambient_" + "raw", exc)
            raw = 0.0
        return raw

    def pressure_read(self):
        prefix_path = self.sensor_dictionnary["pressure"]
        try:
            with open(prefix_path + "in_pressure_" + "raw", "r") as f:
                raw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_pressure_" + "raw", exc)
            raw = 0.0
        return raw

    def accelerometer_read(self):
        # axl_primary = ism330dhcx()
        # axl_data = axl_primary.accelerometer_read()
        prefix_path = self.sensor_dictionnary["accelerometer"]
        # try:
        #    with open(prefix_path + "in_accel_" + 'scale', 'r') as f:
        #        rscale = float(f.read())
        # except Exception as exc:
        #    print("[ERROR] read %s " % prefix_path + "in_accel_" + 'scale', exc)
        #    rscale = 0.0

        rscale = 0.001196

        try:
            with open(prefix_path + "in_accel_" + "x_raw", "r") as f:
                xraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_accel_" + "x_raw", exc)
            xraw = 0.0

        accel_x1 = int(xraw * rscale * 256.0 / 9.81)
        try:
            with open(prefix_path + "in_accel_" + "y_raw", "r") as f:
                yraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_accel_" + "y_raw", exc)
            yraw = 0.0

        accel_y1 = int(yraw * rscale * 256.0 / 9.81)
        try:
            with open(prefix_path + "in_accel_" + "z_raw", "r") as f:
                zraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_accel_" + "z_raw", exc)
            zraw = 0.0

        accel_z1 = int(zraw * rscale * 256.0 / 9.81)
        return [accel_x1, accel_y1, accel_z1]
        # return axl_data

    def sec_accelerometer_read(self):
        prefix_path = self.sensor_dictionnary["sec_accelerometer"]
        # try:
        #     with open(prefix_path + "in_accel_x_" + 'scale', 'r') as f:
        #         rscale = float(f.read())
        # except Exception as exc:
        #     print("[ERROR] read %s " % prefix_path + "in_accel_x_" + 'scale', exc)
        #     rscale = 0.0

        rscale = 0.002392
        try:
            with open(prefix_path + "in_accel_x_" + "raw", "r") as f:
                xraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_accel_x_" + "raw", exc)
            xraw = 0.0

        accel_x = int(xraw * rscale * 256.0 / 9.81)

        try:
            with open(prefix_path + "in_accel_y_" + "scale", "r") as f:
                rscale = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_accel_y_" + "scale", exc)
            rscale = 0.0

        try:
            with open(prefix_path + "in_accel_y_" + "raw", "r") as f:
                yraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_accel_y_" + "raw", exc)
            yraw = 0.0

        accel_y = int(yraw * rscale * 256.0 / 9.81)

        try:
            with open(prefix_path + "in_accel_z_" + "scale", "r") as f:
                rscale = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_accel_z_" + "scale", exc)
            rscale = 0.0

        try:
            with open(prefix_path + "in_accel_z_" + "raw", "r") as f:
                zraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_accel_z_" + "raw", exc)
            zraw = 0.0

        accel_z = int(zraw * rscale * 256.0 / 9.81)
        return [accel_x, accel_y, accel_z]

    def gyroscope_read(self):
        prefix_path = self.sensor_dictionnary["gyroscope"]
        # try:
        #     with open(prefix_path + "in_anglvel_" + 'scale', 'r') as f:
        #         rscale = float(f.read())
        # except Exception as exc:
        #     print("[ERROR] read %s " % prefix_path + "in_anglvel_" + 'scale', exc)
        #     rscale = 0.0

        rscale = 0.000611
        try:
            with open(prefix_path + "in_anglvel_" + "x_raw", "r") as f:
                xraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_anglvel_" + "x_raw", exc)
            xraw = 0.0

        gyro_x = int(xraw * rscale * 256.0 / 9.81)
        try:
            with open(prefix_path + "in_anglvel_" + "y_raw", "r") as f:
                yraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_anglvel_" + "y_raw", exc)
            yraw = 0.0
        gyro_y = int(yraw * rscale * 256.0 / 9.81)
        try:
            with open(prefix_path + "in_anglvel_" + "z_raw", "r") as f:
                zraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_anglvel_" + "z_raw", exc)
            zraw = 0.0
        gyro_z = int(zraw * rscale * 256.0 / 9.81)
        return [gyro_x, gyro_y, gyro_z]

    def magnetometer_read(self):
        prefix_path = self.sensor_dictionnary["magnetometer"]
        try:
            with open(prefix_path + "in_magn_x_" + "scale", "r") as f:
                rscale = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_magn_x_" + "scale", exc)
            rscale = 0.0
        try:
            with open(prefix_path + "in_magn_x_" + "raw", "r") as f:
                xraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_magn_x_" + "raw", exc)
            xraw = 0.0

        mag_x = int(xraw * rscale * 256.0 / 9.81)
        try:
            with open(prefix_path + "in_magn_y_" + "raw", "r") as f:
                yraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_magn_y_" + "raw", exc)
            yraw = 0.0
        mag_y = int(yraw * rscale * 256.0 / 9.81)
        try:
            with open(prefix_path + "in_magn_z_" + "raw", "r") as f:
                zraw = float(f.read())
        except Exception as exc:
            print("[ERROR] read %s " % prefix_path + "in_magn_z_" + "raw", exc)
            zraw = 0.0
        mag_z = int(zraw * rscale * 256.0 / 9.81)
        return [mag_x, mag_y, mag_z]

    def color_sensor_read(self):
        process = subprocess.Popen(
            "./vd6283", stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        rgb = []
        for word in txt.split():
            if word.isdigit():
                rgb.append(int(word))

        # print(rgb)
        # Lux = rgb[0]
        # CCT = rgb[1]

        return rgb

    def proximity_sensor_read(self):
        process = subprocess.Popen(
            ["./tof", "1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        txt = process.stdout.read().decode("utf-8")
        numbers = []
        for word in txt.split():
            if word.isdigit():
                numbers.append(int(word))

        print(numbers)
        distance = numbers[0]

        return distance


# -------------------------------------------------------------------
# -------------------------------------------------------------------
class MainUIWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="X-STM32MP1-MSP01 Sensors")

        # self.set_decorated(False)
        self.maximize()
        self.screen_width = self.get_screen().get_width()
        self.screen_height = self.get_screen().get_height()

        self.set_default_size(self.screen_width, self.screen_height)
        print("[DEBUG] screen size: %dx%d" % (self.screen_width, self.screen_height))
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("destroy", Gtk.main_quit)

        # search sensor interface
        self.sensors = Sensor6s()
        self.sensors.found_all_sensor_path()

        sensor_box = Gtk.VBox(homogeneous=False, spacing=0)

        # temperature
        temp_label = Gtk.Label()
        temp_label.set_markup(
            "<span font_desc='LiberationSans 15'>Temperature(STTS22H)</span>"
        )
        self.temp_value_label = Gtk.Label()
        temp_label.set_use_markup(True)
        # temp_label.set_alignment(0.5, 0.5)
        self.temp_value_label.set_markup(
            "<span font_desc='LiberationSans 15'>--.--  C</span>"
        )
        temp_box = Gtk.HBox(homogeneous=False, spacing=0)
        temp_box.add(temp_label)
        temp_box.add(self.temp_value_label)
        sensor_box.add(temp_box)

        # Pressure
        press_label = Gtk.Label()
        press_label.set_markup(
            "<span font_desc='LiberationSans 15'>Pressure(LPS22H)</span>"
        )
        self.pressure_value_label = Gtk.Label()
        press_label.set_use_markup(True)
        # press_label.set_alignment(0.5, 0.5)
        self.pressure_value_label.set_markup(
            "<span font_desc='LiberationSans 15'>--.-- Pa</span>"
        )
        press_box = Gtk.HBox(homogeneous=False, spacing=0)
        press_box.add(press_label)
        press_box.add(self.pressure_value_label)
        sensor_box.add(press_box)

        # Accel
        accel_label = Gtk.Label()
        accel_label.set_markup(
            "<span font_desc='LiberationSans 15'>Accelerometer(ISM330DHCX)</span>"
        )
        self.accel_value_label = Gtk.Label()
        accel_label.set_use_markup(True)
        # accel_label.set_alignment(0.5, 0.5)
        self.accel_value_label.set_markup(
            "<span font_desc='LiberationSans 15'> [ --.--, --.--, --.--] g</span>"
        )
        accel_box = Gtk.HBox(homogeneous=False, spacing=0)
        accel_box.add(accel_label)
        accel_box.add(self.accel_value_label)
        sensor_box.add(accel_box)

        # Gyroscope
        gyro_label = Gtk.Label()
        gyro_label.set_markup(
            "<span font_desc='LiberationSans 15'>Gyroscope(ISM330DHCX)</span>"
        )
        self.gyro_value_label = Gtk.Label()
        gyro_label.set_use_markup(True)
        # gyro_label.set_alignment(0.5, 0.5)
        self.gyro_value_label.set_markup(
            "<span font_desc='LiberationSans 15'> [ --.--, --.--, --.--] deg/s</span>"
        )
        gyro_box = Gtk.HBox(homogeneous=False, spacing=0)
        gyro_box.add(gyro_label)
        gyro_box.add(self.gyro_value_label)
        sensor_box.add(gyro_box)

        # Magnetometer
        mag_label = Gtk.Label()
        mag_label.set_markup(
            "<span font_desc='LiberationSans 15'>Magnetometer(IIS2MDC)</span>"
        )
        self.mag_value_label = Gtk.Label()
        mag_label.set_use_markup(True)
        # mag_label.set_alignment(0.5, 0.5)
        self.mag_value_label.set_markup(
            "<span font_desc='LiberationSans 15'> [ --.--, --.--, --.--] Gauss</span>"
        )
        mag_box = Gtk.HBox(homogeneous=False, spacing=0)
        mag_box.add(mag_label)
        mag_box.add(self.mag_value_label)
        sensor_box.add(mag_box)

        # Secondary Accelerometer
        sec_accel_label = Gtk.Label()
        sec_accel_label.set_markup(
            "<span font_desc='LiberationSans 15'>Accelerometer2(IIS2DLPC)</span>"
        )
        self.sec_accel_value_label = Gtk.Label()
        sec_accel_label.set_use_markup(True)
        # sec_accel_label.set_alignment(0.5, 0.5)
        self.sec_accel_value_label.set_markup(
            "<span font_desc='LiberationSans 15'> [ --.--, --.--, --.--] g</span>"
        )
        sec_accel_box = Gtk.HBox(homogeneous=False, spacing=0)
        sec_accel_box.add(sec_accel_label)
        sec_accel_box.add(self.sec_accel_value_label)
        sensor_box.add(sec_accel_box)

        # RGB Sensor - VD6283
        color_label = Gtk.Label()
        color_label.set_markup(
            "<span font_desc='LiberationSans 15'>Color Sensor(VD6283)</span>"
        )
        self.color_value_label = Gtk.Label()
        color_label.set_use_markup(True)
        # color_label.set_alignment(0.5, 0.5)
        self.color_value_label.set_markup(
            "<span font_desc='LiberationSans 15'> [ --,--] Lux </span>"
        )
        color_sensor_box = Gtk.HBox(homogeneous=False, spacing=0)
        color_sensor_box.add(color_label)
        color_sensor_box.add(self.color_value_label)
        sensor_box.add(color_sensor_box)

        # ToF Sensor - VL53L5CX
        tof_label = Gtk.Label()
        tof_label.set_markup(
            "<span font_desc='LiberationSans 15'>ToF(VL53L5CX) </span>"
        )
        self.tof_value_label = Gtk.Label()
        tof_label.set_use_markup(True)
        # tof_label.set_alignment(0.5, 0.5)
        self.tof_value_label.set_markup(
            "<span font_desc='LiberationSans 15'> [ --] mm </span>"
        )
        tof_sensor_box = Gtk.HBox(homogeneous=False, spacing=0)
        tof_sensor_box.add(tof_label)
        tof_sensor_box.add(self.tof_value_label)
        sensor_box.add(tof_sensor_box)
        self.add(sensor_box)

        # Add a timer callback to update
        # this takes 2 args: (how often to update in millisec, the method to run)
        GLib.timeout_add(TIME_UPATE, self.update_ui)

    def destroy(self, widget, data=None):
        Gtk.main_quit()

    def update_ui(self):
        # temperature
        temp = self.sensors.temperature_read()
        self.temp_value_label.set_markup(
            "<span font_desc='LiberationSans 15'>%0.2f deg C</span>" % temp
        )
        # print("Temperature>", temp)
        # pressure
        # press = self.sensors.pressure_read() * 0.000024414 * 100;
        # print("Pressure>", press)
        # self.pressure_value_label.set_markup("<span font_desc='LiberationSans 15'>%f Pa</span>" % press)
        # accel
        # accel = self.sensors.accelerometer_read()
        # print("accel>", accel[0], accel[1], accel[2])

        # self.accel_value_label.set_markup(
        #     "<span font_desc='LiberationSans 15'>[ %.02f, %.02f, %.02f] g</span>" % (accel[0], accel[1], accel[2]))
        # # gyro
        # gyro = self.sensors.gyroscope_read()
        # #print("gyro>", gyro[0], gyro[1], gyro[2])

        # self.gyro_value_label.set_markup(
        #     "<span font_desc='LiberationSans 15'>[ %.02f, %.02f, %.02f] deg/s </span>" % (gyro[0], gyro[1], gyro[2]))
        # # mag
        # mag = self.sensors.magnetometer_read()
        # print("mag>", mag[0], mag[1], mag[2])

        self.mag_value_label.set_markup(
            "<span font_desc='LiberationSans 15'>[ %.02f, %.02f, %.02f] gauss</span>"
            % (mag[0], mag[1], mag[2])
        )
        # Secondary Accel
        sec_accel = self.sensors.sec_accelerometer_read()
        # print("sec_accel>", sec_accel[0], sec_accel[1], sec_accel[2])

        self.sec_accel_value_label.set_markup(
            "<span font_desc='LiberationSans 15'>[ %.02f, %.02f, %.02f] g</span>"
            % (sec_accel[0], sec_accel[1], sec_accel[2])
        )

        # Color Sensor
        lux = self.sensors.color_sensor_read()
        print("lux>", lux[0])
        print("lux_cct>", lux[1])

        self.color_value_label.set_markup(
            "<span font_desc='LiberationSans 15'>[ %d , %d ] lux-cct </span>"
            % (lux[0], lux[1])
        )

        # ToF Sensor - VL53L5CX
        distance = self.sensors.proximity_sensor_read()
        print("distance>", distance)

        self.tof_value_label.set_markup(
            "<span font_desc='LiberationSans 15'>[ %d ] mm </span>" % (distance)
        )

        return True


# -------------------------------------------------------------------
# -------------------------------------------------------------------
# Main
if __name__ == "__main__":
    # add signal to catch CRTL+C
    import signal

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    win = MainUIWindow()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()

    Gtk.main()
