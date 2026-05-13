#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

import time
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
chip_z = "/dev/gpiochip9"

import os

def get_pwmchip(timer_addr: str, fallback: str) -> str:
    """
    Dynamically find the pwmchip associated with a specific timer address.
    Returns the fallback if not found.
    """
    pwm_dir = "/sys/class/pwm/"
    if not os.path.exists(pwm_dir):
        return fallback
        
    try:
        for chip in os.listdir(pwm_dir):
            if not chip.startswith("pwmchip"):
                continue
            chip_path = os.path.join(pwm_dir, chip)
            real_path = os.path.realpath(chip_path)
            
            if f"{timer_addr}.timer" in real_path:
                return chip
    except Exception as e:
        print(f"Error resolving PWM chip for {timer_addr}: {e}")
        
    print(f"Warning: Could not find pwmchip for timer {timer_addr}. Using fallback {fallback}.")
    return fallback

pins_1 = {
                "pwm_a": (get_pwmchip("40000000", "pwmchip0"), 3),  # TIM2_CH4 -> PA5
                "pwm_b": (get_pwmchip("40020000", "pwmchip8"), 1),  # TIM4_CH2 -> PA1
                "ref_a": (chip_e, "NA"),
                "ref_b": (chip_a, "NA"),
                "en_a" : (chip_z, 9),
                "en_b" : (chip_z, 0),
                "stdby": (chip_e, "NA"),
                "dir_a": (chip_f, 7),
                "dir_b": (chip_f, 4)
            }

pins_2 = {
                "pwm_a": (get_pwmchip("40030000", "pwmchip12"), 0), # TIM5_CH1 -> PH8
                "pwm_b": (get_pwmchip("40000000", "pwmchip0"), 1),  # TIM2_CH2 -> PF15
                "ref_a": (chip_e, "NA"),
                "ref_b": (chip_a, "NA"),
                "en_a" : (chip_z, 1),
                "en_b" : (chip_z, 6),
                "stdby": (chip_e, "NA"),
                "dir_a": (chip_c, 7),
                "dir_b": (chip_c, 4)
            }

from motor.evspin948_driver import EVSPIN948Driver
spn_motor_1 = EVSPIN948Driver(pins_1)
spn_motor_1.setup_gpio()

spn_motor_2 = EVSPIN948Driver(pins_2)
spn_motor_2.setup_gpio()

def stop():
    spn_motor_1.stop()
    spn_motor_2.stop()

def release():
    try:
        spn_motor_2.end()
    except Exception:
        pass
    try:
        spn_motor_1.end()
    except Exception:
        pass
    
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
        
        


