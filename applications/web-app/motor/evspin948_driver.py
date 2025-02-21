#!/usr/bin/python3
# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

# For simulating UI on PC , please use
# the variable SIMULATE = 1

import sys
import time
from motor.stspin_driver import STSpinDriver
from gpiod.line import Direction, Value
from motor.configurePWM import PWMController
project_name = "X-LINUX-RBT1"
pwm_mode =1


class EVSPIN948Driver(STSpinDriver):
    def __init__(self, pins=None):
        super().__init__()
        if pins is None:
            self.pins = {
                "pwm_a": (self.chip_e, 10),
                "pwm_b": (self.chip_f, 13),
                "ref_a": (self.chip_e, 1),
                "ref_b": (self.chip_a, 12),
                "en_a" : (self.chip_e, 9),
                "en_b" : (self.chip_e, 13),
                "stdby": (self.chip_e, 11),
                "dir_a": (self.chip_d, 15),
                "dir_b": (self.chip_f, 14)
            }
        else:
            self.pins = pins

        self.SIMULATE = 0

    def setup_gpio(self):
        super().setup_gpio()

            
        if pwm_mode ==1 :
            chip, pin = self.pins["pwm_a"]
            self.pwm_a = PWMController(chip, pin)
            self.pwm_a.export_pwm()
            self.pwm_a.set_motor_speed(50,False)
            
            chip, pin = self.pins["pwm_b"]
            if pin != "NA":
                self.pwm_b = PWMController(chip, pin)
                self.pwm_b.export_pwm()
                self.pwm_b.set_motor_speed(50,False)
            
            
        try:
            chip, pin = self.pins["pwm_a"]
            if pin != "NA" and pwm_mode == 0:
                self.lines["pwm_a"] = self.gpio_chips[chip].request_lines(consumer=project_name,config={pin: self.config_output})
            chip, pin = self.pins["pwm_b"]
            if pin != "NA" and pwm_mode == 0:
                self.lines["pwm_b"] = self.gpio_chips[chip].request_lines(consumer=project_name,config={pin: self.config_output})
            chip, pin = self.pins["ref_a"]
            if pin != "NA":
                self.lines["ref_a"] = self.gpio_chips[chip].request_lines(consumer=project_name,config={pin: self.config_output})
            chip, pin = self.pins["ref_b"]
            if pin != "NA":
                self.lines["ref_b"] = self.gpio_chips[chip].request_lines(consumer=project_name,config={pin: self.config_output})
            chip, pin = self.pins["en_a"]
            self.lines["en_a"] = self.gpio_chips[chip].request_lines(consumer=project_name,config={pin: self.config_input})
            chip, pin = self.pins["en_b"]
            self.lines["en_b"] = self.gpio_chips[chip].request_lines(consumer=project_name,config={pin: self.config_input})
            chip, pin = self.pins["stdby"]
            if pin != "NA":    
                self.lines["stdby"] = self.gpio_chips[chip].request_lines(consumer=project_name,config={pin: self.config_output})
            chip, pin = self.pins["dir_a"]
            self.lines["dir_a"] = self.gpio_chips[chip].request_lines(consumer=project_name,config={pin: self.config_output})
            chip, pin = self.pins["dir_b"]
            self.lines["dir_b"] = self.gpio_chips[chip].request_lines(consumer=project_name,config={pin: self.config_output})

            self.set_lines_value(["stdby", "ref_a", "ref_b"], [1, 0, 0])
            self.set_lines_value(["dir_a", "dir_b", "pwm_a", "pwm_b"], [0, 0, 0, 0])

        except Exception as e:
            print(f"An error occurred during GPIO setup: {e}")
            sys.exit(1)

    def current_check(self):
        if self.SIMULATE == 1:
            return 1
        try:
            chip1, pin_a = self.pins["en_a"]
            chip2, pin_b = self.pins["en_b"]
            return (self.lines["en_a"].get_value(pin_a) and self.lines["en_b"].get_value(pin_b))
        except Exception as e:
            print(f"Error reading current state: {e}")
            return None

    def cleanup_gpio(self):
        if self.SIMULATE > 0:
            return
        try:
            for line in self.lines.values():
                line.release()
        except Exception as e:
            print(f"Error during cleanup: {e}")

    def start(self):
        if self.SIMULATE > 0:
            return
        if pwm_mode == 1:
            self.pwm_a.enable_pwm(True)
            self.pwm_b.enable_pwm(True)
        self.is_on = 1
        try:
            self.set_lines_value(["ref_a", "ref_b", "pwm_a", "pwm_b"], [0, 0, 1, 1])
        except Exception as e:
            print(f"Error starting the motor: {e}")

    def stop(self):
        if self.SIMULATE > 0:
            return
        if self.pwm_mode == 1:
            self.pwm_a.enable_pwm(False)
            self.pwm_b.enable_pwm(False)
        self.is_on = 0
        try:
            self.set_lines_value(["pwm_a", "pwm_b"], [0, 0])
        except Exception as e:
            print(f"Error stopping the motor: {e}")

    def right(self):
        if self.SIMULATE > 0:
            return
        
        try:
            if self.current_state != "R" and self.is_on == 1:
                self.stop()
                self.set_lines_value(["pwm_a", "pwm_b"], [0, 0])
                
                

            self.set_lines_value(["dir_a", "dir_b"], [0, 1])

            if self.current_state != "R" and self.is_on == 1:
                self.set_lines_value(["pwm_a", "pwm_b"], [1, 1])
                self.start()
            self.current_state = "R"
        except Exception as e:
            print(f"Error turning right: {e}")

    def left(self):
        if self.SIMULATE > 0:
            return
        try:
            if self.current_state != "L" and self.is_on == 1:
                self.set_lines_value(["pwm_a", "pwm_b"], [0, 0])
                self.stop()
                

            self.set_lines_value(["dir_a", "dir_b"], [1, 0])

            if self.current_state != "L" and self.is_on == 1:
                self.set_lines_value(["pwm_a", "pwm_b"], [1, 1])
                self.start()
            self.current_state = "L"
        except Exception as e:
            print(f"Error turning left: {e}")

    def forward(self):
        if self.SIMULATE > 0:
            return
        try:
            if self.current_state != "F" and self.is_on == 1:
                self.set_lines_value(["pwm_a", "pwm_b"], [0, 0])
                self.stop()

            self.set_lines_value(["dir_a", "dir_b"], [0, 0])

            if self.current_state != "F" and self.is_on == 1:
                self.set_lines_value(["pwm_a", "pwm_b"], [1, 1])
                self.start()
            self.current_state = "F"
        except Exception as e:
            print(f"Error moving forward: {e}")

    def backward(self):
        if self.SIMULATE > 0:
            return
        try:
            if self.current_state != "B" and self.is_on == 1:
                self.set_lines_value(["pwm_a", "pwm_b"], [0, 0])
                self.stop()

            self.set_lines_value(["dir_a", "dir_b"], [1, 1])

            if self.current_state != "B" and self.is_on == 1:
                self.set_lines_value(["pwm_a", "pwm_b"], [1, 1])
                self.start()
            self.current_state = "B"
        except Exception as e:
            print(f"Error moving backward: {e}")

    def end(self):
        if self.SIMULATE > 0:
            return
        self.is_on = 0
        if pwm_mode == 1:
            print("stop")
            self.stop()
            self.pwm_a.unexport_pwm()
            self.pwm_b.unexport_pwm()
        try:
            self.set_lines_value(["ref_a", "ref_a", "pwm_a", "pwm_b", "dir_a", "dir_b"], [0, 0, 0, 0, 0])
        except Exception as e:
            print(f"Error ending the motor operation: {e}")
#for testing
    def rampUp(self,duty=50):
        i=0
        while(i<duty):
            self.pwm_a.set_motor_speed(i)
            self.pwm_b.set_motor_speed(i)
            time.sleep(0.01)
            i=i+1
    def rampDown(self,duty=50):
        i=0
        while(i<=duty):
            self.pwm_a.set_motor_speed(50-i)
            self.pwm_b.set_motor_speed(50-i)
            time.sleep(0.01)
            i=i+1

    def start_a(self,duty=50):
        if self.SIMULATE > 0:
            return
        if pwm_mode == 1:
            self.pwm_a.set_motor_speed(duty)
        self.is_on = 1
        try:
            self.set_lines_value(["ref_a", "ref_b", "pwm_a", "pwm_b"], [0, 0, 1, 1])
        except Exception as e:
            print(f"Error starting the motor: {e}")

    def start_b(self,duty=50):
        if self.SIMULATE > 0:
            return
        if pwm_mode == 1:
            self.pwm_b.set_motor_speed(duty)
        self.is_on = 1
        try:
            self.set_lines_value(["ref_a", "ref_b", "pwm_a", "pwm_b"], [0, 0, 1, 1])
        except Exception as e:
            print(f"Error starting the motor: {e}")

    def stop_a(self):
        if self.SIMULATE > 0:
            return
        if self.pwm_mode == 1:
            self.pwm_a.enable_pwm(False)
        self.is_on = 0
        try:
            self.set_lines_value(["pwm_a", "pwm_b"], [0, 0])
        except Exception as e:
            print(f"Error stopping the motor: {e}")

    def stop_b(self):
        if self.SIMULATE > 0:
            return
        if self.pwm_mode == 1:
            self.pwm_b.enable_pwm(False)
        self.is_on = 0
        try:
            self.set_lines_value(["pwm_a", "pwm_b"], [0, 0])
        except Exception as e:
            print(f"Error stopping the motor: {e}")

    def forward_a(self):
        if self.SIMULATE > 0:
            return
        try:
            if self.current_state != "F" and self.is_on == 1:
                self.set_lines_value(["pwm_a"], [0])
                self.stop()

            self.set_lines_value(["dir_a"], [0])

            if self.current_state != "F" and self.is_on == 1:
                self.set_lines_value(["pwm_a",], [1])
                self.start()
            self.current_state = "F"
        except Exception as e:
            print(f"Error moving forward: {e}")

    def forward_b(self):
        if self.SIMULATE > 0:
            return
        try:
            if self.current_state != "F" and self.is_on == 1:
                self.set_lines_value(["pwm_b"], [0])
                self.stop()

            self.set_lines_value(["dir_b"], [0])

            if self.current_state != "F" and self.is_on == 1:
                self.set_lines_value(["pwm_b",], [1])
                self.start()
            self.current_state = "F"
        except Exception as e:
            print(f"Error moving forward: {e}")
            
    def reverse_b(self):
        if self.SIMULATE > 0:
            return
        try:
            if self.current_state != "F" and self.is_on == 1:
                self.set_lines_value(["pwm_b"], [0])
                self.stop()

            self.set_lines_value(["dir_b"], [1])

            if self.current_state != "F" and self.is_on == 1:
                self.set_lines_value(["pwm_b",], [1])
                self.start()
            self.current_state = "F"
        except Exception as e:
            print(f"Error moving forward: {e}")
    
    def reverse_a(self):
        if self.SIMULATE > 0:
            return
        try:
            if self.current_state != "F" and self.is_on == 1:
                self.set_lines_value(["pwm_a"], [0])
                self.stop()

            self.set_lines_value(["dir_a"], [1])

            if self.current_state != "F" and self.is_on == 1:
                self.set_lines_value(["pwm_a",], [1])
                self.start()
            self.current_state = "F"
        except Exception as e:
            print(f"Error moving forward: {e}")
