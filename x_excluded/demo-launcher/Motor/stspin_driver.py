#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

# For simulating UI on PC , please use
# the variable SIMULATE = 1

import time
import sys
import gpiod
from gpiod.line import Direction, Value
from Motor.pwm_controller import PWMController

pwm_mode =1



class STSpinDriver:
    def __init__(self):
        self.current_state = "F"
        self.pwm_mode = pwm_mode 
        self.is_on = 0

        
        if self.pwm_mode == 1:
            self.pwm_chip_0 = "pwmchip0"
            self.pwm_chip_4 = "pwmchip4"
            self.pwm_chip_8 = "pwmchip8"
            self.pwm_chip_12 = "pwmchip12"
            
        self.chip_a = "/dev/gpiochip0"
        self.chip_b = "/dev/gpiochip1"
        self.chip_c = "/dev/gpiochip2"
        self.chip_d = "/dev/gpiochip3"
        self.chip_e = "/dev/gpiochip4"
        self.chip_f = "/dev/gpiochip5"
        self.chip_g = "/dev/gpiochip6"
        self.chip_h = "/dev/gpiochip7"
        self.chip_i = "/dev/gpiochip8"
        

        self.pins = {}

    def set_lines_value(self, line_names, values):
        try:
            for line_name, value in zip(line_names, values):
                
                chip, pin = self.pins[line_name]
                if pin != "NA" and line_name !="pwm_a" and line_name !="pwm_b" :
                    
                    if value == 1:
                        self.lines[line_name].set_value(pin, Value.ACTIVE)
                    elif value == 0:
                        self.lines[line_name].set_value(pin, Value.INACTIVE)
        except Exception as e:
            print(f"Error setting lines: {e}")
    
    
    def setup_gpio(self):
        
        try:
            self.gpiod = gpiod
            
            self.gpio_chips = {
                chip: gpiod.Chip(chip) 
                for chip in {chip for chip, _ in self.pins.values() if chip.startswith('/dev')}
            }

            self.lines = {
                name: self.gpio_chips[chip] 
                for name, (chip, pin) in self.pins.items() 
                if chip.startswith('/dev')
            }

            self.config_output = gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE)
            self.config_input = gpiod.LineSettings(direction=Direction.INPUT, output_value=Value.ACTIVE)


        except ImportError:
            print("gpiod not found")
        except Exception as e:
            print(f"An error occurred during GPIO setup: {e}")
            sys.exit(1)
    

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def reset(self):
        self.current_state = "F"
        self.is_on = 0

    def right(self):
        raise NotImplementedError

    def left(self):
        raise NotImplementedError

    def forward(self):
        raise NotImplementedError

    def backward(self):
        raise NotImplementedError

    def cleanup(self):
        raise NotImplementedError
