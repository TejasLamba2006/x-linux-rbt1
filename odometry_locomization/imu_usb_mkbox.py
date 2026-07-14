# imu_usb_mkbox.py — STEVAL-MKBOXPRO (SensorTile.box PRO) gyroscope over USB,
# used as an external yaw source since the robot's own onboard IMU doesn't
# ACK on i2c-1 (see imu_lsm6dsv16x.py).
#
# Split-transport protocol, reverse-engineered live against the box (DATALOG2
# firmware, advertises as HSD2v3x over BLE):
#   - Commands (incl. "start streaming") ALWAYS go over BLE's PnPL command
#     characteristic, even when the actual sensor data is routed over USB.
#     Direct USB bulk writes to the command-shaped OUT endpoint (0x06) were
#     tried and always came back STALL (EPIPE) -- USB is data-out only here.
#   - Once "log_controller*start_log" is sent over BLE with
#     {"interface": 1}, the box's USB interface (vendor id 0x0483:0x5744,
#     "Sensortile.box_PRO_Multi_Sensor_Streaming") starts pushing continuous
#     data on bulk IN endpoints 0x81-0x85, one endpoint per active sensor
#     stream (matches each sensor's "ep_id" from get_status).
#   - Endpoint 0x81 (gyro's ep_id=0) was confirmed live by rotating the box
#     and watching its raw values spike from near-zero (~-33) to ~2000+ and
#     decay back after stopping -- the other endpoints (accel, likely
#     pressure/mic) stayed comparatively flat during the same rotation.
#   - Payload on 0x81 is a raw back-to-back stream of signed int16 LE
#     (gx, gy, gz) triples, no per-sample header/timestamp -- unlike some of
#     the other endpoints (0x83 had a 5-byte counter prefix per read).
#   - Scale factor (0.14 dps/LSB) is NOT guessed -- it's the exact
#     "multiply_factor" the box itself reported for lsm6dsv16x_gyro via
#     {"get_status":"lsm6dsv16x_gyro"} over BLE.
#
# ponytail: axis order/sign (which of gx/gy/gz is "up" on this box, and
# whether any axis is inverted vs. the robot's mounting) is unverified --
# only gz is used here as the yaw-rate axis, matching a box mounted flat.
# Rotate the box while it's actually fixed to the robot and check the sign
# in run_linux.py's HUD if yaw goes the wrong direction.

import asyncio
import struct

import usb.core
from bleak import BleakClient

BLE_DEVICE_NAME = "HSD2v33"  # update if the box's advertised name changes
CMD_CHAR_UUID = "0000001b-0002-11e1-ac36-0002a5d5c51b"  # COPY_PNPLIKE_CHAR_UUID

USB_VENDOR_ID = 0x0483
USB_PRODUCT_ID = 0x5744
GYRO_EP = 0x82

GYRO_MDPS_PER_LSB = 140.0  # 0.14 dps/LSB, per the box's own reported multiply_factor

# BLE_COMM_TP framing (ST's chunked-write protocol for the PnPL command
# characteristic -- see imu_ble_mkbox.py's header note / prior probing).
_TP_START, _TP_START_END, _TP_MIDDLE, _TP_END = 0x00, 0x20, 0x40, 0x80


def _encode_tp(payload: bytes, mtu_payload=17):
    if len(payload) <= mtu_payload:
        return [bytes([_TP_START_END]) + struct.pack(">H", len(payload)) + payload]
    chunks = [bytes([_TP_START]) + struct.pack(">H",
                                               len(payload)) + payload[:mtu_payload]]
    rest = payload[mtu_payload:]
    while len(rest) > mtu_payload:
        chunks.append(bytes([_TP_MIDDLE]) + rest[:mtu_payload])
        rest = rest[mtu_payload:]
    chunks.append(bytes([_TP_END]) + rest)
    return chunks


class MkBoxUsbGyro:
    def __init__(self, ble_device_name=BLE_DEVICE_NAME):
        self.ble_device_name = ble_device_name
        self._ble_client = None
        self._usb_dev = None

    async def start(self, scan_timeout=10.0):
        """Connect over BLE just long enough to start USB streaming, then open the USB device."""
        from bleak import BleakScanner

        device = await BleakScanner.find_device_by_name(self.ble_device_name, scan_timeout)
        if device is None:
            raise RuntimeError(
                f"MKBOXPRO '{self.ble_device_name}' not found in BLE scan")
        self._ble_client = BleakClient(device)
        await self._ble_client.connect()
        await self._ble_client.start_notify(CMD_CHAR_UUID, lambda *_: None)

        cmd = '{"log_controller*start_log":{"interface":1}}'
        for chunk in _encode_tp(cmd.encode()):
            await self._ble_client.write_gatt_char(CMD_CHAR_UUID, chunk, response=False)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)

        self._usb_dev = usb.core.find(
            idVendor=USB_VENDOR_ID, idProduct=USB_PRODUCT_ID)
        if self._usb_dev is None:
            raise RuntimeError("MKBOXPRO USB streaming interface not found")
        if self._usb_dev.is_kernel_driver_active(0):
            self._usb_dev.detach_kernel_driver(0)
        self._usb_dev.set_configuration()

    def read_gyro_dps(self, timeout_ms=200):
        """Returns a list of (gx, gy, gz) dps tuples decoded from one USB bulk read (may be empty)."""
        try:
            raw = bytes(self._usb_dev.read(GYRO_EP, 64, timeout=timeout_ms))
        except usb.core.USBError:
            return []
        n_samples = len(raw) // 6
        samples = []
        for i in range(n_samples):
            gx, gy, gz = struct.unpack_from("<hhh", raw, i * 6)
            samples.append((
                gx * GYRO_MDPS_PER_LSB / 1000.0,
                gy * GYRO_MDPS_PER_LSB / 1000.0,
                gz * GYRO_MDPS_PER_LSB / 1000.0,
            ))
        return samples

    async def stop(self):
        if self._ble_client is not None and self._ble_client.is_connected:
            await self._ble_client.disconnect()
