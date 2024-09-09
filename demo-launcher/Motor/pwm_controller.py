class PWMController:
    def __init__(self, pwm_chip, pwm_channel):
        self.pwm_chip = pwm_chip
        self.pwm_channel = pwm_channel
        self.pwm_path = f"/sys/class/pwm/{pwm_chip}/pwm{pwm_channel}"
    
    def export_pwm(self):
        with open(f"/sys/class/pwm/{self.pwm_chip}/export", "w") as f:
            f.write(str(self.pwm_channel))

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
        period_ns = 50000  # 1 ms period for example
        duty_cycle_ns = int(period_ns * (speed_percent / 100))
        self.set_pwm_period(period_ns)
        self.set_pwm_duty_cycle(duty_cycle_ns)
        self.enable_pwm(value)

    def stop_motor(self):
        self.enable_pwm(False)
