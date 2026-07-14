# gyro_fixed_test.py -- test the fixed decoder (5-byte header strip + timestamp validation)
# Run on board: python3 gyro_fixed_test.py [seconds]
import asyncio
import sys
import time

from imu_usb_mkbox import MkBoxUsbGyro, GYRO_MDPS_PER_LSB

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0


def stats(vals):
    n = len(vals)
    if n == 0:
        return 0, 0, 0, 0
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    return mean, var ** 0.5, min(vals), max(vals)


async def main():
    gyro = MkBoxUsbGyro()
    print("starting stream (BLE cmd -> USB data)...")
    await gyro.start()
    print(f"capturing {DURATION}s at rest -- DO NOT MOVE THE ROBOT")

    xs, ys, zs = [], [], []
    t0 = time.time()
    while time.time() - t0 < DURATION:
        for gx, gy, gz in gyro.read_gyro_dps():
            xs.append(gx)
            ys.append(gy)
            zs.append(gz)
    dt = time.time() - t0

    n = len(zs)
    print(f"\nsamples: {n}  rate: {n/dt:.0f} Hz  duration: {dt:.1f}s")
    if n:
        for name, vals in (("gx", xs), ("gy", ys), ("gz", zs)):
            m, s, lo, hi = stats(vals)
            print(f"{name}: mean {m:+8.3f}  std {s:7.3f}  min {lo:+9.2f}  max {hi:+9.2f} dps")
        # Show distribution of gz (the yaw axis)
        bins = [0] * 20  # -10 to +10 dps in 1 dps bins
        for v in zs:
            idx = int(v + 10)
            if 0 <= idx < 20:
                bins[idx] += 1
        print("\ngz distribution (1 dps bins, -10 to +10):")
        for i, c in enumerate(bins):
            bar = '#' * (c * 40 // max(bins) if max(bins) > 0 else 0)
            print(f"  {i-10:+3d}: {c:5d} {bar}")
        # Count outliers
        outliers = sum(1 for v in zs if abs(v) > 5)
        print(f"\ngz samples with |value| > 5 dps: {outliers} ({100*outliers/n:.1f}%)")
    await gyro.stop()

asyncio.run(main())
