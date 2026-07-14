# gyro_rest_test.py -- isolated MKBOXPRO gyro sanity check (robot at rest).
# Captures N seconds of decoded samples, prints per-axis mean/std/min/max,
# measured sample rate, and flags suspicious 256-multiple raw values
# (byte-misalignment artifacts). Run on the board: python3 gyro_rest_test.py [seconds]
import asyncio
import sys
import time

from imu_usb_mkbox import MkBoxUsbGyro, GYRO_MDPS_PER_LSB

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0


def stats(vals):
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    return mean, var ** 0.5, min(vals), max(vals)


async def main():
    gyro = MkBoxUsbGyro()
    print("starting stream (BLE cmd -> USB data)...")
    await gyro.start()
    print(f"capturing {DURATION}s at rest -- DO NOT MOVE THE ROBOT")

    xs, ys, zs = [], [], []
    misaligned = 0
    t0 = time.time()
    while time.time() - t0 < DURATION:
        for gx, gy, gz in gyro.read_gyro_dps():
            xs.append(gx)
            ys.append(gy)
            zs.append(gz)
            for v in (gx, gy, gz):
                raw = round(v * 1000.0 / GYRO_MDPS_PER_LSB)
                if raw != 0 and raw % 256 == 0:
                    misaligned += 1
    dt = time.time() - t0

    n = len(zs)
    print(f"\nsamples: {n}  rate: {n/dt:.0f} Hz")
    if n:
        for name, vals in (("gx", xs), ("gy", ys), ("gz", zs)):
            m, s, lo, hi = stats(vals)
            print(f"{name}: mean {m:+8.3f}  std {s:7.3f}  min {lo:+9.2f}  max {hi:+9.2f} dps")
        print(f"raw values that are exact 256-multiples: {misaligned} "
              f"({100.0*misaligned/(3*n):.2f}% of axis-values)")
    await gyro.stop()

asyncio.run(main())
