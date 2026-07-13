# calibrate_linux.py — raw-evdev COUNTS_PER_CM calibration for the HP 320M, Linux/OpenSTLinux only.
#
# Does not touch run_linux.py's capture pipeline; reuses its struct/const definitions so the
# byte-level parsing can't drift out of sync between the two scripts.
#
# Usage: python3 calibrate_linux.py /dev/input/event1 100
#   Push the mouse in a straight line over a known distance (cm) with BTN_LEFT held down,
#   release when done. Repeat a few times (Ctrl+C to stop) and compare results.

import struct
import sys
import time

from run_linux import (
    INPUT_EVENT_FMT, INPUT_EVENT_SIZE,
    EV_REL, EV_KEY, REL_X, REL_Y, BTN_LEFT,
)


def calibrate(device_path: str, distance_cm: float):
    fd = open(device_path, "rb")
    print(f"[calibrate] Opened {device_path}. Hold LEFT CLICK, move exactly {distance_cm} cm, release.")
    print("[calibrate] Ctrl+C to stop.")

    dx = dy = 0
    recording = False

    while True:
        raw = fd.read(INPUT_EVENT_SIZE)
        if len(raw) < INPUT_EVENT_SIZE:
            continue
        _, _, ev_type, ev_code, ev_value = struct.unpack(INPUT_EVENT_FMT, raw)

        if ev_type == EV_KEY and ev_code == BTN_LEFT:
            if ev_value == 1:
                dx = dy = 0
                recording = True
                print("[calibrate] recording...")
            elif ev_value == 0 and recording:
                recording = False
                counts = (dx ** 2 + dy ** 2) ** 0.5
                if counts == 0:
                    print("[calibrate] no movement detected, ignored")
                    continue
                counts_per_cm = counts / distance_cm
                print(f"[calibrate] dx={dx} dy={dy} counts={counts:.1f} -> COUNTS_PER_CM={counts_per_cm:.2f}")
                with open("calibration_results.txt", "a") as f:
                    f.write(
                        f"{time.strftime('%Y-%m-%d %H:%M:%S')} evdev_raw "
                        f"distance_cm={distance_cm} counts={counts:.1f} CountsPerCM={counts_per_cm:.2f}\n"
                    )
        elif ev_type == EV_REL and recording:
            if ev_code == REL_X:
                dx += ev_value
            elif ev_code == REL_Y:
                dy += ev_value


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 calibrate_linux.py <device_path> <distance_cm>")
        sys.exit(1)
    calibrate(sys.argv[1], float(sys.argv[2]))
