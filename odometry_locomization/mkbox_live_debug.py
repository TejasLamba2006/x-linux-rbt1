#!/usr/bin/env python3
"""
mkbox_live.py -- manual live inspector for the STEVAL-MKBOXPRO's USB data
streams, so you can eyeball which endpoint is really the gyro instead of
trusting a remote guess.

Run directly on the board:  python3 /tmp/mkbox_live.py

What it does:
  1. Connects over BLE and sends {"log_controller*start_log":{"interface":1}}
     (commands only work over BLE on this firmware -- USB writes to the
     command endpoint STALL, confirmed by direct testing).
  2. Polls all 5 USB bulk IN endpoints (0x81-0x85) in a loop and prints each
     one's raw bytes AND a couple of int16-LE decodings, refreshed in place,
     so you can rotate/tilt/shake the box and watch which endpoint's numbers
     actually move in response.

Ctrl+C to stop (also sends stop_log so the box doesn't keep logging to SD).
"""
import asyncio
import struct
import sys
import threading
import time

import usb.core
from bleak import BleakClient, BleakScanner

BLE_DEVICE_NAME = "HSD2v33"  # change here if the box's advertised name differs
CMD_UUID = "0000001b-0002-11e1-ac36-0002a5d5c51b"
USB_VENDOR_ID = 0x0483
USB_PRODUCT_ID = 0x5744
ENDPOINTS = [0x81, 0x82, 0x83, 0x84, 0x85]

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


def decode_int16le(raw: bytes, n=6):
    """First n int16-LE values, for a quick eyeball of magnitude/sign."""
    count = min(n, len(raw) // 2)
    return struct.unpack_from(f"<{count}h", raw)


latest = {ep: b"" for ep in ENDPOINTS}
counts = {ep: 0 for ep in ENDPOINTS}
lock = threading.Lock()


def usb_poll_thread(stop_event):
    dev = usb.core.find(idVendor=USB_VENDOR_ID, idProduct=USB_PRODUCT_ID)
    if dev is None:
        print("[USB] device not found -- is it plugged in?")
        stop_event.set()
        return
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
    dev.set_configuration()
    while not stop_event.is_set():
        for ep in ENDPOINTS:
            try:
                d = bytes(dev.read(ep, 64, timeout=50))
                with lock:
                    latest[ep] = d
                    counts[ep] += 1
            except usb.core.USBError:
                pass


def print_loop(stop_event):
    while not stop_event.is_set():
        time.sleep(0.3)
        with lock:
            snapshot = {ep: (latest[ep], counts[ep]) for ep in ENDPOINTS}
        sys.stdout.write("\033[2J\033[H")  # clear screen
        print("=== MKBOXPRO live USB endpoints (Ctrl+C to stop) ===")
        print("Rotate / tilt / shake the box and watch which line's numbers react.\n")
        for ep in ENDPOINTS:
            raw, n = snapshot[ep]
            vals = decode_int16le(raw)
            print(f"EP {hex(ep)}  reads={n:6d}  bytes={len(raw):2d}  "
                  f"hex={raw.hex()[:32]}")
            print(f"          int16 (first {len(vals)}): {vals}")
        sys.stdout.flush()


async def main():
    print(f"Scanning for '{BLE_DEVICE_NAME}'...")
    device = await BleakScanner.find_device_by_name(BLE_DEVICE_NAME, 10.0)
    if device is None:
        print(f"'{BLE_DEVICE_NAME}' not found. Is BLE advertising on? "
              f"(check the name matches what's currently advertised)")
        return

    async with BleakClient(device, timeout=20.0) as client:
        print("BLE connected, starting USB log stream...")
        await client.start_notify(CMD_UUID, lambda *_: None)
        await asyncio.sleep(0.3)
        for chunk in encode_tp(b'{"log_controller*start_log":{"interface":1}}'):
            await client.write_gatt_char(CMD_UUID, chunk, response=False)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)

        stop_event = threading.Event()
        t_usb = threading.Thread(target=usb_poll_thread, args=(stop_event,), daemon=True)
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
            print("\nStopping log...")
            for chunk in encode_tp(b'{"log_controller*stop_log":{"interface":1}}'):
                await client.write_gatt_char(CMD_UUID, chunk, response=False)
                await asyncio.sleep(0.05)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
