# imu_usb_mkbox.py — STEVAL-MKBOXPRO (SensorTile.box PRO) gyro + accel over USB
#
# Split-transport protocol (DATALOG2 firmware, HSD2v3x BLE name):
#   - Commands ALWAYS go over BLE PnPL characteristic, even when sensor data
#     is routed over USB. Once log_controller*start_log is accepted with
#     {"interface":1}, the box streams over USB on its own — no BLE needed.
#   - USB interface 0x0483:0x5744, one bulk IN endpoint per active sensor:
#     endpoint address = 0x81 + ep_id (from get_status response).
#     Gyro ep_id=0 → 0x81, Accel ep_id=1 → 0x82.
#   - Wire format: [N raw samples][8-byte double timestamp][N samples]...
#     Each sample is 6 bytes (3× int16 LE). The 8-byte timestamp interrupts
#     every samples_per_ts samples and must be skipped. A persistent byte
#     buffer + sample counter handles both the timestamp skip and USB read
#     boundary alignment (64-byte reads aren't sample-aligned).
#   - Scale factors from get_status: gyro 0.14 dps/LSB, accel 0.061 mg/LSB.
#
# ponytail: axis order/sign is unverified — only gz (yaw-rate) and accel
# gravity are used here. Check sign in run_linux.py HUD if yaw is wrong.

import asyncio
import struct

import usb.core
from bleak import BleakClient

BLE_DEVICE_NAME = "HSD2v33"
CMD_CHAR_UUID = "0000001b-0002-11e1-ac36-0002a5d5c51b"

USB_VENDOR_ID = 0x0483
USB_PRODUCT_ID = 0x5744

# Gyro endpoint (ep_id=0 → 0x81)
GYRO_EP = 0x81
GYRO_SAMPLES_PER_TS = 1000
GYRO_MDPS_PER_LSB = 140.0  # 0.14 dps/LSB

# Accel endpoint (ep_id=1 → 0x82)
ACCEL_EP = 0x82
ACCEL_SAMPLES_PER_TS = 1000
ACCEL_MG_PER_LSB = 0.061   # mg/LSB at ±2g range

_USB_HEADER_SIZE = 5

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


class _StreamDecoder:
    """Decodes one USB endpoint's sample stream (handles timestamp skip +
    byte buffer alignment)."""

    def __init__(self, samples_per_ts, sensitivity):
        self.spts = samples_per_ts
        self.sensitivity = sensitivity
        self._buf = bytearray()
        self._sample_count = 0

    def feed_and_decode(self, raw: bytes):
        """Feed raw USB bytes, return list of decoded sample tuples (float)."""
        if len(raw) <= _USB_HEADER_SIZE:
            return []
        self._buf.extend(raw[_USB_HEADER_SIZE:])

        samples = []
        while True:
            if self._sample_count >= self.spts:
                if len(self._buf) < 8:
                    break
                (ts,) = struct.unpack_from("<d", self._buf, 0)
                if not (0 < ts < 1e6):
                    del self._buf[:6]
                    self._sample_count = max(0, self._sample_count - 1)
                    continue
                del self._buf[:8]
                self._sample_count = 0
                continue
            if len(self._buf) < 6:
                break
            raw_vals = struct.unpack_from("<hhh", self._buf, 0)
            del self._buf[:6]
            self._sample_count += 1
            samples.append(tuple(v * self.sensitivity for v in raw_vals))
        return samples


class MkBoxUsbGyro:
    def __init__(self, ble_device_name=BLE_DEVICE_NAME):
        self.ble_device_name = ble_device_name
        self._usb_dev = None
        self._gyro = _StreamDecoder(GYRO_SAMPLES_PER_TS, GYRO_MDPS_PER_LSB / 1000.0)
        self._accel = _StreamDecoder(ACCEL_SAMPLES_PER_TS, ACCEL_MG_PER_LSB)

    async def start(self, scan_timeout=10.0):
        """Connect over BLE just long enough to start USB streaming, then
        disconnect BLE entirely and open the USB device."""
        from bleak import BleakScanner

        device = await BleakScanner.find_device_by_name(self.ble_device_name, scan_timeout)
        if device is None:
            raise RuntimeError(
                f"MKBOXPRO '{self.ble_device_name}' not found in BLE scan")
        ble_client = BleakClient(device)
        await ble_client.connect()
        await ble_client.start_notify(CMD_CHAR_UUID, lambda *_: None)

        cmd = '{"log_controller*start_log":{"interface":1}}'
        for chunk in _encode_tp(cmd.encode()):
            await ble_client.write_gatt_char(CMD_CHAR_UUID, chunk, response=False)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)
        await ble_client.disconnect()

        self._usb_dev = usb.core.find(
            idVendor=USB_VENDOR_ID, idProduct=USB_PRODUCT_ID)
        if self._usb_dev is None:
            raise RuntimeError("MKBOXPRO USB streaming interface not found")
        if self._usb_dev.is_kernel_driver_active(0):
            self._usb_dev.detach_kernel_driver(0)
        self._usb_dev.set_configuration()

    def read_gyro_dps(self, timeout_ms=200):
        """Returns a list of (gx, gy, gz) dps tuples from the gyro endpoint."""
        try:
            raw = bytes(self._usb_dev.read(GYRO_EP, 4096, timeout=timeout_ms))
        except usb.core.USBError:
            return []
        return self._gyro.feed_and_decode(raw)

    def read_accel_mg(self, timeout_ms=200):
        """Returns a list of (ax, ay, az) mg tuples from the accel endpoint."""
        try:
            raw = bytes(self._usb_dev.read(ACCEL_EP, 4096, timeout=timeout_ms))
        except usb.core.USBError:
            return []
        return self._accel.feed_and_decode(raw)

    def read_gyro_and_accel(self, timeout_ms=200):
        """Read both endpoints in one call. Returns (gyro_samples, accel_samples)
        where gyro_samples is [(gx,gy,gz) dps] and accel_samples is [(ax,ay,az) mg]."""
        return self.read_gyro_dps(timeout_ms), self.read_accel_mg(timeout_ms)

    async def stop(self):
        """Reconnect briefly over BLE to send stop_log."""
        from bleak import BleakScanner

        device = await BleakScanner.find_device_by_name(self.ble_device_name, 10.0)
        if device is None:
            return
        async with BleakClient(device) as ble_client:
            await ble_client.start_notify(CMD_CHAR_UUID, lambda *_: None)
            cmd = '{"log_controller*stop_log":{"interface":1}}'
            for chunk in _encode_tp(cmd.encode()):
                await ble_client.write_gatt_char(CMD_CHAR_UUID, chunk, response=False)
                await asyncio.sleep(0.05)
