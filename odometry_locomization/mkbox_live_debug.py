#!/usr/bin/env python3
"""
mkbox_live.py -- manual live inspector for the STEVAL-MKBOXPRO's USB gyro
stream, with CORRECT byte-stream framing this time.

Two bugs in the first version of this script (and the first imu_usb_mkbox.py
driver) made every endpoint look like garbage:
  1. USB bulk reads return up to 64 bytes at a time, but samples are 6 bytes
     (3x int16) -- 64 is not a multiple of 6, so treating each independent
     64-byte read as starting fresh at a sample boundary silently drifted
     the byte alignment by 4 bytes on every single read.
  2. Per DATALOG2's own firmware source (DatalogAppTask.c), the wire format
     is actually [samples_per_ts raw samples][8-byte double timestamp]
     [more samples]... -- confirmed live via get_status: lsm6dsv16x_gyro
     has samples_per_ts=1000, so at its actual streamed rate a timestamp
     block interrupts the sample stream roughly every 2-3 seconds. Any
     capture longer than that hit an un-skipped 8-byte timestamp treated as
     more sample data, permanently desyncing everything after it.

This version keeps one persistent byte buffer per endpoint across reads and
tracks a per-endpoint sample counter to correctly skip the 8-byte timestamp
exactly every samples_per_ts samples, using each sensor's real dim/dtype/
samples_per_ts pulled live from get_status instead of assumed.

Run directly on the board: python3 /tmp/mkbox_live.py
"""
import asyncio
import struct
import sys
import threading
import time

import usb.core
from bleak import BleakClient, BleakScanner

BLE_DEVICE_NAME = "HSD2v33"  # change if the box's advertised name differs
CMD_UUID = "0000001b-0002-11e1-ac36-0002a5d5c51b"
USB_VENDOR_ID = 0x0483
USB_PRODUCT_ID = 0x5744

START, START_END, MIDDLE, END = 0x00, 0x20, 0x40, 0x80


def encode_tp(payload: bytes, mtu_payload=17):
    if len(payload) <= mtu_payload:
        return [bytes([START_END]) + struct.pack(">H", len(payload)) + payload]
    chunks = [bytes([START]) + struct.pack(">H", len(payload)) + payload[:mtu_payload]]
    rest = payload[mtu_payload:]
    while len(rest) > mtu_payload:
        chunks.append(bytes([MIDDLE]) + rest[:mtu_payload])
        rest = rest[mtu_payload:]
    chunks.append(bytes([END]) + rest)
    return chunks


SENSOR_NAMES = [
    "lsm6dsv16x_gyro", "lsm6dsv16x_acc", "lps22df_press", "stts22h_temp",
    "mp23db01hp_mic", "lis2du12_acc",
]


class SensorStreamDecoder:
    """Tracks one endpoint's continuous byte buffer + sample/timestamp framing."""

    def __init__(self, name, dim, dtype, samples_per_ts, sensitivity):
        self.name = name
        self.dim = dim
        self.dtype = dtype  # "int16" or "float_t"
        self.sample_bytes = dim * (2 if dtype == "int16" else 4)
        self.spts = max(1, samples_per_ts)
        self.sensitivity = sensitivity
        self.buf = bytearray()
        self.sample_count = 0
        self.last_values = None
        self.n_samples_seen = 0

    def feed(self, raw: bytes):
        self.buf.extend(raw)
        while True:
            if self.sample_count >= self.spts:
                if len(self.buf) < 8:
                    break
                del self.buf[:8]  # skip the 8-byte double timestamp
                self.sample_count = 0
                continue
            if len(self.buf) < self.sample_bytes:
                break
            chunk = bytes(self.buf[:self.sample_bytes])
            del self.buf[:self.sample_bytes]
            self.sample_count += 1
            self.n_samples_seen += 1
            if self.dtype == "int16":
                vals = struct.unpack(f"<{self.dim}h", chunk)
            else:
                vals = struct.unpack(f"<{self.dim}f", chunk)
            self.last_values = tuple(v * self.sensitivity for v in vals)


decoders = {}  # ep -> SensorStreamDecoder
lock = threading.Lock()


async def fetch_sensor_configs(client):
    results = {}

    def on_notify(_, data):
        hdr = data[0]
        payload = data[1:]
        if not hasattr(on_notify, "buf"):
            on_notify.buf = bytearray()
        if hdr in (START, START_END):
            on_notify.buf.clear()
        on_notify.buf.extend(payload)
        if hdr in (START_END, END):
            import json
            try:
                obj = json.loads(bytes(on_notify.buf).rstrip(b"\x00").decode())
                for k, v in obj.items():
                    if isinstance(v, dict) and "ep_id" in v:
                        results[k] = v
            except Exception:
                pass

    await client.start_notify(CMD_UUID, on_notify)
    await asyncio.sleep(0.3)
    for name in SENSOR_NAMES:
        for chunk in encode_tp(f'{{"get_status":"{name}"}}'.encode()):
            await client.write_gatt_char(CMD_UUID, chunk, response=False)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.4)
    return results


def usb_poll_thread(stop_event, ep_map):
    dev = usb.core.find(idVendor=USB_VENDOR_ID, idProduct=USB_PRODUCT_ID)
    if dev is None:
        print("[USB] device not found -- is it plugged in?")
        stop_event.set()
        return
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
    dev.set_configuration()
    while not stop_event.is_set():
        for ep in ep_map:
            try:
                d = bytes(dev.read(ep, 64, timeout=50))
                with lock:
                    decoders[ep].feed(d)
            except usb.core.USBError:
                pass


def print_loop(stop_event):
    while not stop_event.is_set():
        time.sleep(0.3)
        sys.stdout.write("\033[2J\033[H")
        print("=== MKBOXPRO live USB gyro/accel/press/temp (Ctrl+C to stop) ===")
        print("Rotate / tilt / shake the box and watch which line's numbers react.\n")
        with lock:
            for ep, dec in decoders.items():
                print(f"EP {hex(ep)}  {dec.name:18s}  n={dec.n_samples_seen:7d}  "
                      f"values={dec.last_values}")
        sys.stdout.flush()


async def main():
    print(f"Scanning for '{BLE_DEVICE_NAME}'...")
    device = await BleakScanner.find_device_by_name(BLE_DEVICE_NAME, 10.0)
    if device is None:
        print(f"'{BLE_DEVICE_NAME}' not found.")
        return

    ep_map = {}
    async with BleakClient(device, timeout=20.0) as client:
        print("BLE connected. Reading sensor configs...")
        configs = await fetch_sensor_configs(client)

        for name, cfg in configs.items():
            if cfg.get("ep_id", -1) < 0:
                continue
            ep = 0x81 + cfg["ep_id"]
            ep_map[ep] = SensorStreamDecoder(
                name, cfg["dim"], cfg["data_type"],
                cfg["samples_per_ts"], cfg["sensitivity"],
            )
            print(f"  {name}: ep_id={cfg['ep_id']} -> USB EP {hex(ep)}, "
                  f"dim={cfg['dim']}, dtype={cfg['data_type']}, "
                  f"spts={cfg['samples_per_ts']}, sensitivity={cfg['sensitivity']}")

        if not ep_map:
            print("No active sensor streams found (nothing enabled?).")
            return
        decoders.update(ep_map)

        print("\nStarting USB log stream...")
        for chunk in encode_tp(b'{"log_controller*start_log":{"interface":1}}'):
            await client.write_gatt_char(CMD_UUID, chunk, response=False)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.3)
    # BLE disconnected here (end of `async with`) -- USB keeps streaming on
    # its own once start_log is accepted, no need to hold the BLE link open.
    print("BLE disconnected, USB streaming continues on its own.")

    stop_event = threading.Event()
    t_usb = threading.Thread(target=usb_poll_thread, args=(stop_event, ep_map), daemon=True)
    t_print = threading.Thread(target=print_loop, args=(stop_event,), daemon=True)
    t_usb.start()
    t_print.start()

    try:
        while True:
            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        print("\nReconnecting over BLE to stop logging...")
        device = await BleakScanner.find_device_by_name(BLE_DEVICE_NAME, 10.0)
        if device is not None:
            async with BleakClient(device, timeout=20.0) as client:
                await client.start_notify(CMD_UUID, lambda *_: None)
                for chunk in encode_tp(b'{"log_controller*stop_log":{"interface":1}}'):
                    await client.write_gatt_char(CMD_UUID, chunk, response=False)
                    await asyncio.sleep(0.05)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
