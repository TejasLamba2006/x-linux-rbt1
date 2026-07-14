# imu_ble_mkbox.py — STEVAL-MKBOXPRO (SensorTile.box PRO) gyroscope over BLE,
# used as an external yaw source since the robot's own onboard IMU doesn't
# ACK on i2c-1 (see imu_lsm6dsv16x.py). The box has its own working
# LSM6DSV16X gyro and streams it wirelessly instead.
#
# Talks ST's BlueST protocol (UM2496) directly via bleak (BlueZ D-Bus) --
# NOT the official BlueSTSDK_Python (that one's pinned to bluepy + old Python
# and multiple ST community reports say it fails to even discover modern
# boards; bleak is the community-confirmed working path for this exact box).
#
# ponytail: requires the box to be running BLE-streaming firmware (BLE
# Sensor Demo / STSW-MKBOX-BLEDK), NOT the stock HSDatalog2 firmware it may
# ship with -- HSDatalog2's BLE channel is config/log-control only and does
# not stream live sensor samples (confirmed by directly probing it: its
# log_controller*start_log command never acks for any interface value).
#
# BlueST UUID pattern: XXXXXXXX-0001-11e1-ac36-0002a5d5c51b, where XXXXXXXX
# is a bitmask of the feature(s) packed into that characteristic.
# 0x00400000 = gyroscope alone (UM2496 / BlueSTSDK_Python ble_node_definitions).
# Payload: 2-byte timestamp + int16 x,y,z (little-endian), in mdps.

import asyncio
import struct

from bleak import BleakClient, BleakScanner

DEVICE_NAME = "STB_PRO"  # BLE Sensor Demo firmware's advertised name
GYRO_CHAR_UUID = "00400000-0001-11e1-ac36-0002a5d5c51b"

# ponytail: BlueST classic feature convention -- raw int16 is mdps, so
# dps = raw / 1000. Verify against a known rotation once the box is live;
# adjust here if the demo firmware reports a different fixed-point scale.
MDPS_PER_LSB = 1.0


class MkBoxGyro:
    """Connects to a STEVAL-MKBOXPRO over BLE and streams gyro-Z (dps) via a callback."""

    def __init__(self, device_name=DEVICE_NAME):
        self.device_name = device_name
        self._client = None

    async def connect(self, scan_timeout=10.0):
        device = await BleakScanner.find_device_by_name(self.device_name, scan_timeout)
        if device is None:
            raise RuntimeError(
                f"MKBOXPRO '{self.device_name}' not found in BLE scan")
        self._client = BleakClient(device)
        await self._client.connect()

    async def stream_gyro(self, on_sample):
        """on_sample(gx_dps, gy_dps, gz_dps) called on every notification."""

        def handler(_, data: bytearray):
            # 2-byte timestamp + 3x int16, little-endian
            _, gx, gy, gz = struct.unpack("<Hhhh", bytes(data[:8]))
            on_sample(gx * MDPS_PER_LSB / 1000.0, gy *
                      MDPS_PER_LSB / 1000.0, gz * MDPS_PER_LSB / 1000.0)

        await self._client.start_notify(GYRO_CHAR_UUID, handler)

    async def disconnect(self):
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()
