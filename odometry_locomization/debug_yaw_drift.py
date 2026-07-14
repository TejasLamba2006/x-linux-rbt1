#!/usr/bin/env python3
"""
Debug yaw drift: polls /state from the local Flask server (port 5000)
and logs yaw, mag_heading, recording, gyro_bias to a CSV + live terminal.
Leave the robot completely still. Run for 30-60 s.
"""
import urllib.request
import time
import csv
import sys

URL = "http://127.0.0.1:5000/state"
CSV = "/tmp/yaw_drift_debug.csv"
DURATION = 60  # seconds

def main():
    print(f"Logging yaw drift for {DURATION}s — keep robot still")
    print(f"{'time':>7} {'yaw':>8} {'rec':>4}")
    print("-" * 25)

    t0 = time.time()
    rows = []

    with open(CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["elapsed_s", "yaw", "recording"])

        while time.time() - t0 < DURATION:
            try:
                with urllib.request.urlopen(URL, timeout=2) as resp:
                    data = __import__("json").loads(resp.read())
                yaw = data.get("yaw", "?")
                rec = data.get("recording", "?")
                elapsed = time.time() - t0

                writer.writerow([f"{elapsed:.2f}", yaw, rec])
                rows.append((elapsed, yaw, rec))

                print(f"{elapsed:7.2f} {yaw:8} {rec!s:>4}")
                time.sleep(0.2)
            except Exception as e:
                print(f"  error: {e}")
                time.sleep(0.5)

    # Summary
    if rows:
        yaws = [r[1] for r in rows if isinstance(r[1], (int, float))]
        if yaws:
            drift = yaws[-1] - yaws[0]
            print(f"\nYaw started: {yaws[0]:.2f}  ended: {yaws[-1]:.2f}  drift: {drift:.2f} deg over {DURATION}s")
            print(f"CSV saved to {CSV}")

if __name__ == "__main__":
    main()
