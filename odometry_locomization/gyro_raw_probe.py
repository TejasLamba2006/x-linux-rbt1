# gyro_raw_probe.py -- reverse the MKBOXPRO USB wire framing empirically.
# Reads large bulk transfers from EP 0x81 with the box AT REST and reports:
# read sizes, first-bytes structure (header/counter?), and which byte offset
# makes the int16 sample stream look like a real at-rest gyro (tiny values).
# Run on board: python3 gyro_raw_probe.py
import asyncio
import struct
import time

import usb.core

from imu_usb_mkbox import MkBoxUsbGyro, GYRO_EP

N_READS = 40
READ_SIZE = 16384


async def main():
    g = MkBoxUsbGyro()
    print("starting stream via BLE...")
    await g.start()
    dev = g._usb_dev

    reads = []
    for _ in range(N_READS):
        try:
            reads.append(bytes(dev.read(GYRO_EP, READ_SIZE, timeout=500)))
        except usb.core.USBError as e:
            print("read err:", e)
    sizes = [len(r) for r in reads]
    print(f"\nread sizes: min {min(sizes)} max {max(sizes)} "
          f"uniq {sorted(set(sizes))[:10]}")

    print("\nfirst 24 bytes of first 6 reads:")
    for r in reads[:6]:
        print(" ", r[:24].hex(" "))

    # header hypothesis: byte0 = stream id, bytes1..4 = LE u32 counter
    print("\nbyte0 / u32@1 of each read:")
    for r in reads[:10]:
        print(f"  b0={r[0]:#04x}  ctr={struct.unpack_from('<I', r, 1)[0]}")

    # find the offset that makes at-rest int16 triplets tiny
    r = reads[5]
    print("\nmean |raw int16| for payload starting at each offset 0..15:")
    for off in range(16):
        vals = struct.unpack_from(f"<{(len(r)-off)//2}h", r, off)
        vals = vals[:600]
        mean_abs = sum(abs(v) for v in vals) / len(vals)
        print(f"  off {off:2d}: mean|raw| {mean_abs:9.1f}")

    # look for an 8-byte double timestamp anywhere in one read
    print("\nplausible doubles (0 < v < 1e6) in read[5], step 1:")
    hits = 0
    for off in range(0, len(r) - 8):
        (v,) = struct.unpack_from("<d", r, off)
        if 1e-3 < v < 1e6 and v == v:
            print(f"  off {off}: {v:.6f}")
            hits += 1
            if hits >= 10:
                break

    await g.stop()

asyncio.run(main())
