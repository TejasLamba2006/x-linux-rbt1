# gyro_full_decode.py -- comprehensive MKBOXPRO USB gyro decoder test.
# Properly handles: 5-byte USB packet header, 8-byte double timestamp
# interleaved every 1000 samples, byte-alignment across reads.
# Run on board: python3 gyro_full_decode.py
import asyncio
import struct
import time

import usb.core

from imu_usb_mkbox import (MkBoxUsbGyro, GYRO_EP, GYRO_MDPS_PER_LSB,
                            GYRO_SAMPLES_PER_TS)

N_READS = 50
READ_SIZE = 16384
HEADER_SIZE = 5  # 1 byte stream-id + 4 byte LE u32 counter


def decode_with_timestamp_skip(payload, header_size, samples_per_ts, label=""):
    """Decode int16 triplets from payload, skipping 8-byte double timestamps
    every samples_per_ts samples. Returns list of (gz dps) values."""
    buf = bytearray(payload[header_size:])
    sc = 0
    gz_vals = []
    ts_found = 0
    while len(buf) >= 6:
        if sc >= samples_per_ts:
            if len(buf) < 8:
                break
            (ts,) = struct.unpack_from("<d", buf, 0)
            # Unix timestamps: 1e8 to 2e9; boot timestamps: 0 to 1e6
            if 0 < ts < 2e9:
                del buf[:8]
                sc = 0
                ts_found += 1
                continue
        gx, gy, gz = struct.unpack_from("<hhh", buf, 0)
        del buf[:6]
        sc += 1
        gz_vals.append(gz * GYRO_MDPS_PER_LSB / 1000.0)
    return gz_vals, ts_found


async def main():
    g = MkBoxUsbGyro()
    print("starting stream via BLE...")
    await g.start()
    dev = g._usb_dev

    # Collect raw reads
    reads = []
    for _ in range(N_READS):
        try:
            reads.append(bytes(dev.read(GYRO_EP, READ_SIZE, timeout=500)))
        except usb.core.USBError:
            pass
    print(f"collected {len(reads)} reads, sizes: {[len(r) for r in reads[:10]]}")

    # === Test 1: strip 5-byte header from each read, concatenate, decode ===
    print("\n=== Test 1: header-per-read + timestamp skip ===")
    payload = b"".join(r[HEADER_SIZE:] for r in reads)
    for spt in [992, 996, 1000, 1004]:
        gz, ts = decode_with_timestamp_skip(
            b"\x00" * HEADER_SIZE + payload, HEADER_SIZE, spt)
        if gz:
            mean = sum(gz) / len(gz)
            std = (sum((v - mean)**2 for v in gz) / len(gz)) ** 0.5
            print(f"  spt={spt}: n={len(gz):5d}  mean_gz={mean:+8.3f}  "
                  f"std={std:7.3f}  timestamps_skipped={ts}")

    # === Test 2: no per-read header, just concatenate raw reads ===
    print("\n=== Test 2: no header, timestamp skip on concatenated stream ===")
    payload = b"".join(reads)
    for spt in [992, 996, 1000, 1004]:
        gz, ts = decode_with_timestamp_skip(
            b"\x00\x00\x00\x00\x00" + payload, 5, spt)
        if gz:
            mean = sum(gz) / len(gz)
            std = (sum((v - mean)**2 for v in gz) / len(gz)) ** 0.5
            print(f"  spt={spt}: n={len(gz):5d}  mean_gz={mean:+8.3f}  "
                  f"std={std:7.3f}  timestamps_skipped={ts}")

    # === Test 3: try reading WITHOUT the header skip, treating data as
    #     raw stream with timestamps detected by value range ===
    print("\n=== Test 3: no header, search for ANY 8-byte double in stream ===")
    payload = b"".join(reads)
    # Find all doubles in a wide range
    ts_positions = []
    for off in range(0, len(payload) - 8, 1):
        (v,) = struct.unpack_from("<d", payload, off)
        if 1e-3 < v < 3e9:
            ts_positions.append((off, v))
    print(f"  found {len(ts_positions)} plausible doubles in {len(payload)} bytes")
    if ts_positions:
        for pos, val in ts_positions[:15]:
            print(f"    offset {pos}: {val:.2f}")
        # Check spacing between timestamps
        if len(ts_positions) > 1:
            spacings = [ts_positions[i+1][0] - ts_positions[i][0]
                       for i in range(min(20, len(ts_positions)-1))]
            print(f"  spacings between timestamps: {spacings[:15]}")

    # === Test 4: the current imu_usb_mkbox.py decoder, just to baseline ===
    print("\n=== Test 4: current decoder baseline (read 64 bytes at a time) ===")
    g2 = MkBoxUsbGyro()
    await g2.start()
    t0 = time.time()
    gz_vals = []
    while time.time() - t0 < 5:
        for gx, gy, gz in g2.read_gyro_dps():
            gz_vals.append(gz)
    dt = time.time() - t0
    if gz_vals:
        mean = sum(gz_vals) / len(gz_vals)
        std = (sum((v - mean)**2 for v in gz_vals) / len(gz_vals)) ** 0.5
        print(f"  n={len(gz_vals):5d}  rate={len(gz_vals)/dt:.0f}Hz  "
              f"mean_gz={mean:+8.3f}  std={std:7.3f} dps")
    await g2.stop()

asyncio.run(main())
