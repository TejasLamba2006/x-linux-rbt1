# imu_iis2mdc.py — IIS2MDC onboard magnetometer (STM32MP257F-DK + X-STM32MP-RBT01),
# used as the yaw source in place of the ISM330DHCX gyro (which doesn't ACK on
# this unit -- see board bring-up notes). Confirmed alive on i2c-1 @ 0x1e,
# WHO_AM_I=0x40, via direct i2cget during bring-up.
#
# Unlike gyro integration, a magnetometer gives an *absolute* heading straight
# from Earth's field vector -- no dead-reckoning drift -- at the cost of being
# sensitive to nearby ferrous metal/motor magnets and needing the board roughly
# level (tilt compensation not implemented; ponytail: add it via the
# accelerometer's gravity vector if the robot ever operates on a slope).
#
# Register map per ST's iis2mdc_reg.h. Uses raw ioctl on /dev/i2c-N (stdlib
# os/fcntl) instead of smbus2, matching imu_lsm6dsv16x.py's approach.

import fcntl
import os
import struct

I2C_BUS = 1                 # board_utils.sh: I2C_BUS_PRIMARY (same bus as the IMU)
DEVICE_ADDR = 0x1E          # fixed address, confirmed via i2cdetect -y 1
I2C_SLAVE = 0x0703          # linux/i2c-dev.h ioctl request

WHO_AM_I_REG = 0x4F
WHO_AM_I_EXPECTED = 0x40    # confirmed via i2cget during bring-up

CFG_REG_A = 0x60             # MD (mode) + ODR + COMP_TEMP_EN
CFG_REG_C = 0x62             # BDU

OUTX_L_REG = 0x68            # X low byte; Y/Z follow at +2/+4

SENSITIVITY_MGAUSS = 1.5    # mgauss/LSB, fixed full-scale +-50 gauss


class IIS2MDC:
    def __init__(self, bus_num=I2C_BUS, addr=DEVICE_ADDR):
        self.addr = addr
        self.fd = os.open(f"/dev/i2c-{bus_num}", os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, self.addr)

    def _read_byte(self, reg):
        os.write(self.fd, bytes([reg]))
        return os.read(self.fd, 1)[0]

    def _write_byte(self, reg, value):
        os.write(self.fd, bytes([reg, value]))

    def check_who_am_i(self):
        return self._read_byte(WHO_AM_I_REG) == WHO_AM_I_EXPECTED

    def configure(self):
        self._write_byte(CFG_REG_C, 0x10)   # BDU=1 (bit4)
        # comp_temp_en=1 (bit7), ODR=100Hz (bits3:2=11), MD=continuous (bits1:0=00)
        self._write_byte(CFG_REG_A, 0x8C)

    def read_mag_mgauss(self):
        os.write(self.fd, bytes([OUTX_L_REG]))
        raw = os.read(self.fd, 6)
        sx, sy, sz = struct.unpack("<hhh", raw)  # signed 16-bit, little-endian
        return (
            sx * SENSITIVITY_MGAUSS,
            sy * SENSITIVITY_MGAUSS,
            sz * SENSITIVITY_MGAUSS,
        )

    def close(self):
        os.close(self.fd)
