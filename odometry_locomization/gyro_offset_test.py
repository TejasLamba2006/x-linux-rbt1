# gyro_offset_test.py -- test different header offsets to find the correct
# byte alignment for MKBOXPRO USB gyro samples.
# The raw probe showed odd offsets give mean|raw|=1.6 vs even offsets ~414,
# suggesting the current decoder (offset 0) is wrong.
# Run on board: python3 gyro_offset_test.py
import asyncio
import struct
import time

import usb.core

from imu_usb_mkbox import (MkBoxUsbGyro, GYRO_EP, GYRO_MDPS_PER_LSB,
                            GYRO_SAMPLES_PER_TS)

N_READS = 20
READ_SIZE = 16384


async def main():
    g = MkBoxUsbGyro()
    print("starting stream via BLE...")
    await g.start()
    dev = g._usb_dev

    # Collect raw USB reads
    reads = []
    for _ in range(N_READS):
        try:
            reads.append(bytes(dev.read(GYRO_EP, READ_SIZE, timeout=500)))
        except usb.core.USBError:
            pass
    print(f"collected {len(reads)} reads")

    # Concatenate all reads into one big buffer
    big = b"".join(reads)
    print(f"total bytes: {len(big)}")

    # Test each possible header size (0..20 bytes) and see which gives
    # the smallest mean |raw int16| (i.e. closest to zero at rest)
    print("\n--- testing header sizes 0..20 ---")
    best_off = 0
    best_mean = 999999
    for hdr in range(21):
        vals = []
        # skip the header, then read int16s from the rest
        payload = big[hdr:]
        n_samples = min(len(payload) // 2, 6000)
        raw_int16s = struct.unpack_from(f"<{n_samples}h", payload, 0)
        # convert to dps and compute mean absolute
        for v in raw_int16s:
            dps = v * GYRO_MDPS_PER_LSB / 1000.0
            vals.append(abs(dps))
        mean_abs = sum(vals) / len(vals) if vals else 999999
        marker = ""
        if mean_abs < best_mean:
            best_mean = mean_abs
            best_off = hdr
            marker = " <-- BEST"
        print(f"  header={hdr:2d}: mean|dps|={mean_abs:7.3f}  (first 6 raw int16: "
              f"{raw_int16s[:6]}){marker}")

    print(f"\nbest header size: {best_off} bytes (mean|dps|={best_mean:.3f})")

    # Now try with timestamp-skip logic at the best offset
    print(f"\n--- testing timestamp skip with header={best_off} ---")
    payload = big[best_off:]
    # Try different samples_per_ts values
    for spt in [992, 994, 996, 998, 1000, 1002, 1004]:
        buf = bytearray(payload)
        sc = 0
        dps_vals = []
        while len(buf) >= 6:
            if sc >= spt:
                if len(buf) < 8:
                    break
                # check if the 8 bytes look like a plausible double timestamp
                (ts,) = struct.unpack_from("<d", buf, 0)
                if 1e-3 < ts < 1e9:
                    del buf[:8]
                    sc = 0
                    continue
                else:
                    # not a timestamp, treat as samples
                    pass
            gx, gy, gz = struct.unpack_from("<hhh", buf, 0)
            del buf[:6]
            sc += 1
            dps_vals.append(gz * GYRO_MDPS_PER_LSB / 1000.0)
        if dps_vals:
            mean_d = sum(dps_vals) / len(dps_vals)
            std_d = (sum((v - mean_d)**2 for v in dps_vals) / len(dps_vals)) ** 0.5
            print(f"  spt={spt}: n={len(dps_vals):5d}  mean_gz={mean_d:+8.3f}  "
                  f"std={std_d:7.3f} dps")

    await g.stop()

asyncio.run(main())
