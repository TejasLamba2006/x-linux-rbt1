#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

# This script configures the PWM settings for a motor controller.
# It sets the PWM period and duty cycle, and provides methods to enable
# or disable the PWM signal. The script also includes methods to set
# the motor speed and stop the motor.
class PWMController:
    def __init__(self, pwm_chip, pwm_channel):
        self.pwm_chip = pwm_chip
        self.pwm_channel = pwm_channel
        self.pwm_path = f"/sys/class/pwm/{pwm_chip}/pwm{pwm_channel}"
    
    def export_pwm(self):
        import os
        if os.path.exists(self.pwm_path):
            return
        try:
            with open(f"/sys/class/pwm/{self.pwm_chip}/export", "w") as f:
                f.write(str(self.pwm_channel))
        except OSError:
            if os.path.exists(self.pwm_path):
                return
            raise

    def unexport_pwm(self):
        with open(f"/sys/class/pwm/{self.pwm_chip}/unexport", "w") as f:
            f.write(str(self.pwm_channel))

    def set_pwm_period(self, period_ns):
        with open(f"{self.pwm_path}/period", "w") as f:
            f.write(str(period_ns))

    def set_pwm_duty_cycle(self, duty_cycle_ns):
        with open(f"{self.pwm_path}/duty_cycle", "w") as f:
            f.write(str(duty_cycle_ns))

    def enable_pwm(self, enable=True):
        with open(f"{self.pwm_path}/enable", "w") as f:
            f.write("1" if enable else "0")

    # Motor control methods
    def set_motor_speed(self, speed_percent, value = True):
        period_ns = 500000  # 1 ms period for example
        duty_cycle_ns = int(period_ns * (speed_percent / 100))
        # A channel left exported by a crashed run keeps its old duty_cycle;
        # if that's bigger than the new period the kernel rejects the period
        # write with EINVAL (duty_cycle can never exceed period). Zero it
        # first so the period write always succeeds regardless of leftover
        # hardware state.
        self.set_pwm_duty_cycle(0)
        self.set_pwm_period(period_ns)
        self.set_pwm_duty_cycle(duty_cycle_ns)
        self.enable_pwm(value)

    def stop_motor(self):
        self.enable_pwm(False)
