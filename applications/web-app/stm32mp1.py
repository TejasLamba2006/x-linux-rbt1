#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

import time
#import pwm
import threading

exit_flag = False

chip_a = "/dev/gpiochip0"
chip_b = "/dev/gpiochip1"
chip_c = "/dev/gpiochip2"
chip_d = "/dev/gpiochip3"
chip_e = "/dev/gpiochip4"
chip_f = "/dev/gpiochip5"
chip_g = "/dev/gpiochip6"
chip_h = "/dev/gpiochip7"
chip_i = "/dev/gpiochip8"


pins_1 = {
                "pwm_a": ("pwmchip4", 1),
                "pwm_b": ("pwmchip0", 1),
                "ref_a": (chip_e, "NA"),
                "ref_b": (chip_a, "NA"),
                "en_a" : (chip_d, 7),
                "en_b" : (chip_g, 15),
                "stdby": (chip_e, "NA"),
                "dir_a": (chip_f, 7),
                "dir_b": (chip_f, 6)
            }

pins_2 = {
                "pwm_a": ("pwmchip8", 1),
                "pwm_b": ("pwmchip12", 0),
                "ref_a": (chip_e, "NA"),
                "ref_b": (chip_a, "NA"),
                "en_a" : (chip_f, 1),
                "en_b" : (chip_f, 0),
                "stdby": (chip_e, "NA"),
                "dir_a": (chip_f, 9),
                "dir_b": (chip_f, 8)
            }

from motor.evspin948_driver import EVSPIN948Driver
spn_motor_1 = EVSPIN948Driver(pins_1)
spn_motor_1.setup_gpio()

spn_motor_2 = EVSPIN948Driver(pins_2)
spn_motor_2.setup_gpio()

def stop():
    print("stop")
    spn_motor_1.stop()
    spn_motor_2.stop()

def release():
    spn_motor_2.end()
    spn_motor_1.end()
    
def rampUp():
    spn_motor_1.rampUp()
    spn_motor_2.rampUp()

def rampDown():
    spn_motor_1.rampDown()
    spn_motor_2.rampDown()

def motor_1a(duty = 50, dir =0 ):
    spn_motor_1.start_a(duty)
    if dir == 0:
        spn_motor_1.forward_a()
    elif dir == 1:
        spn_motor_1.reverse_a()
        
def motor_1b(duty = 50, dir =0 ):
    spn_motor_1.start_b(duty)
    if dir == 0:
        spn_motor_1.forward_b()
    elif dir == 1:
        spn_motor_1.reverse_b()
        
def motor_2a(duty = 50, dir =0 ):
    spn_motor_2.start_a(duty)
    if dir == 0:
        spn_motor_2.forward_a()
    elif dir == 1:
        spn_motor_2.reverse_a()
        
def motor_2b(duty = 50, dir =0 ):
    spn_motor_2.start_b(duty)
    if dir == 0:
        spn_motor_2.forward_b()
    elif dir == 1:
        spn_motor_2.reverse_b()

