# imu_lsm6dsv16x.py — LSM6DSV16X onboard IMU (STM32MP257F-DK), gyro-Z yaw
# source + accelerometer (used for stationary detection / gyro-bias tracking).
#
# Register map/config mirrors lsm6dsv16x.sh + board_utils.sh (accel config and
# I2C_BUS_PRIMARY=1 / DEVICE_ADDR_LSM6DV16X=0x6B come straight from there);
# this adds the gyroscope config+read since yaw needs angular rate, not tilt.
#
# Uses raw ioctl on /dev/i2c-N (stdlib os/fcntl) instead of smbus2, to avoid a
# new dependency for a handful of registers.

import fcntl
import os
import struct

I2C_BUS = 1                 # board_utils.sh: I2C_BUS_PRIMARY
DEVICE_ADDR = 0x6B          # board_utils.sh: DEVICE_ADDR_LSM6DV16X (SA0 tied high)
I2C_SLAVE = 0x0703          # linux/i2c-dev.h ioctl request

WHO_AM_I_REG = 0x0F
WHO_AM_I_EXPECTED = 0x70    # 112 decimal, per lsm6dsv16x.sh

CTRL1 = 0x10                 # ODR_XL / OP_MODE_XL (accelerometer)
CTRL2 = 0x11                 # ODR_G / OP_MODE_G (gyroscope)
CTRL3 = 0x12                 # BDU | IF_INC
CTRL6 = 0x15                 # FS_G full-scale bits (gyroscope)
CTRL8 = 0x17                 # FS_XL full-scale bits (accelerometer)

OUTX_L_A = 0x28               # accelerometer X low byte; Y/Z follow at +2/+4
OUTZ_L_G = 0x26               # gyroscope Z low byte, OUTZ_H_G follows at +1

FS_500DPS_SENSITIVITY_MDPS = 17.50  # mdps/LSB @ +-500 dps (ST 16-bit gyro standard table)
FS_2G_SENSITIVITY_MG = 0.061        # mg/LSB @ +-2 g, per lsm6dsv16x.sh


class LSM6DSV16X:
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
        self._write_byte(CTRL3, 0x44)   # BDU=1, IF_INC=1 (multi-byte reads coherent)
        self._write_byte(CTRL6, 0x02)   # FS_G = +-500 dps
        self._write_byte(CTRL2, 0x06)   # ODR_G = 120 Hz, high-performance mode
        self._write_byte(CTRL8, 0x00)   # FS_XL = +-2 g
        self._write_byte(CTRL1, 0x06)   # ODR_XL = 120 Hz, high-performance mode

    def read_gyro_z_dps(self):
        os.write(self.fd, bytes([OUTZ_L_G]))
        raw = os.read(self.fd, 2)
        val = struct.unpack("<h", raw)[0]  # signed 16-bit, little-endian
        return val * FS_500DPS_SENSITIVITY_MDPS / 1000.0

    def read_accel_mg(self):
        os.write(self.fd, bytes([OUTX_L_A]))
        raw = os.read(self.fd, 6)
        sx, sy, sz = struct.unpack("<hhh", raw)  # signed 16-bit, little-endian
        return (
            sx * FS_2G_SENSITIVITY_MG,
            sy * FS_2G_SENSITIVITY_MG,
            sz * FS_2G_SENSITIVITY_MG,
        )

    def close(self):
        os.close(self.fd)
