# imu_usb_mkbox.py — STEVAL-MKBOXPRO (SensorTile.box PRO) gyroscope over USB,
# used as an external yaw source since the robot's own onboard IMU doesn't
# ACK on i2c-1 (see imu_lsm6dsv16x.py).
#
# Split-transport protocol, reverse-engineered live against the box (DATALOG2
# firmware, advertises as HSD2v3x over BLE) and cross-checked against the
# actual firmware source (STMicroelectronics/fp-sns-datalog2,
# DatalogAppTask.c):
#   - Commands (incl. "start streaming") ALWAYS go over BLE's PnPL command
#     characteristic, even when the actual sensor data is routed over USB.
#     Direct USB bulk writes to the command-shaped OUT endpoint (0x06) were
#     tried and always came back STALL (EPIPE) -- USB is data-out only here.
#     Once "log_controller*start_log" is accepted with {"interface": 1}, the
#     box keeps streaming over USB on its own, so the BLE connection is
#     dropped immediately after -- no need to hold it open.
#   - USB interface is vendor id 0x0483:0x5744 ("Sensortile.box_PRO_Multi_
#     Sensor_Streaming"), one bulk IN endpoint per active sensor stream:
#     endpoint address = 0x81 + ep_id, where ep_id comes from that sensor's
#     {"get_status":"<name>"} response. lsm6dsv16x_gyro reports ep_id=0, so
#     gyro data is on 0x81 -- confirmed live (see mkbox_live_debug.py) by
#     rotating the box and watching ONLY that endpoint's decoded values
#     track the motion and settle back near zero afterward.
#   - Wire format per DatalogAppTask.c is NOT a flat stream of samples:
#     [samples_per_ts raw samples][8-byte double timestamp][more samples]...
#     samples_per_ts for the gyro is 1000 (from get_status), and at its
#     streamed rate that timestamp block interrupts the stream every ~2-3s --
#     long enough to corrupt any capture that doesn't skip it. Also, USB
#     bulk reads return up to 64 bytes at a time but samples are 6 bytes (3x
#     int16), and 64 isn't a multiple of 6, so treating each independent
#     read as sample-aligned silently drifts the byte offset every read.
#     Both are handled here with a persistent per-stream byte buffer and a
#     sample counter that skips exactly 8 bytes every samples_per_ts samples.
#   - Scale factor (0.14 dps/LSB) is NOT guessed -- it's the exact
#     "multiply_factor"/"sensitivity" the box itself reported for
#     lsm6dsv16x_gyro via {"get_status":"lsm6dsv16x_gyro"} over BLE.
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
GYRO_EP_ID = 0  # from get_status:lsm6dsv16x_gyro -- USB endpoint is 0x81 + ep_id
GYRO_EP = 0x81 + GYRO_EP_ID

GYRO_SAMPLES_PER_TS = 1000  # from get_status:lsm6dsv16x_gyro -- how the 8-byte
                            # timestamp is interleaved into the sample stream
GYRO_MDPS_PER_LSB = 140.0  # 0.14 dps/LSB, per the box's own reported multiply_factor

# Fixed per-sample time interval, derived from get_status:lsm6dsv16x_gyro's
# own "usb_dps" (bytes/sec actually streamed over USB): 2304 / 6 bytes-per-
# sample = 384 samples/sec. Used instead of wall-clock time.time() per
# sample for yaw integration -- read_gyro_dps() often returns a whole batch
# of samples decoded from one USB read (data arrives faster than we poll),
# and timing each sample in that batch by wall-clock time makes every
# sample after the first look like it took ~0s (just loop overhead),
# wildly under-integrating bursts. The real time between consecutive
# samples is this fixed interval, not however long the Python loop took.
GYRO_SAMPLE_INTERVAL_S = 6.0 / 2304.0

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
        self._usb_dev = None
        self._buf = bytearray()
        self._sample_count = 0

    async def start(self, scan_timeout=10.0):
        """Connect over BLE just long enough to start USB streaming, then
        disconnect BLE entirely and open the USB device -- once
        log_controller*start_log has been accepted, the box keeps streaming
        over USB on its own; it doesn't need a live BLE connection held for
        that."""
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
        """Returns a list of (gx, gy, gz) dps tuples decoded from whatever's
        newly arrived, correctly stitched across USB read boundaries and
        with the periodic 8-byte timestamp block skipped (see module header
        for why both of those matter -- may be empty)."""
        try:
            raw = bytes(self._usb_dev.read(GYRO_EP, 64, timeout=timeout_ms))
        except usb.core.USBError:
            return []

        self._buf.extend(raw)
        samples = []
        while True:
            if self._sample_count >= GYRO_SAMPLES_PER_TS:
                if len(self._buf) < 8:
                    break
                del self._buf[:8]  # skip the 8-byte double timestamp
                self._sample_count = 0
                continue
            if len(self._buf) < 6:
                break
            gx, gy, gz = struct.unpack_from("<hhh", self._buf, 0)
            del self._buf[:6]
            self._sample_count += 1
            samples.append((
                gx * GYRO_MDPS_PER_LSB / 1000.0,
                gy * GYRO_MDPS_PER_LSB / 1000.0,
                gz * GYRO_MDPS_PER_LSB / 1000.0,
            ))
        return samples

    async def stop(self):
        """Reconnect briefly over BLE to send stop_log -- USB streaming has
        no live BLE connection to tear down (see start())."""
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
