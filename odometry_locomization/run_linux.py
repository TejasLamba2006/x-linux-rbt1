# server.py  ── Linux / OpenSTLinux version (STM32MP257F-DK)
import asyncio
import math
import os
import socket
import struct
import threading
import time
from collections import deque
from flask import Flask, jsonify, request, send_from_directory

# ── Constants ─────────────────────────────────────────────────────────────────
COUNTS_PER_CM = 25
UDP_PORT = 2055
EMA_ALPHA = 0.3
SMOOTHING_WIN = 5

# Linux input_event layout (64-bit kernel, ARM64)
# struct input_event { timeval(8+8), type(2), code(2), value(4) } = 24 bytes
INPUT_EVENT_FMT = "llHHi"
INPUT_EVENT_SIZE = struct.calcsize(INPUT_EVENT_FMT)

# /linux/input-event-codes.h
EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02

REL_X = 0x00
REL_Y = 0x01

BTN_LEFT = 272
BTN_RIGHT = 273

app = Flask(__name__, static_folder=".")

# ── Shared State ──────────────────────────────────────────────────────────────
lock = threading.Lock()
state = {
    "x":         0.0,
    "y":         0.0,
    "yaw":       0.0,
    "distance":  0.0,
    "recording": False,
    "path":      [[0.0, 0.0]],
}

_raw_dx_buf = deque(maxlen=SMOOTHING_WIN)
_ema_distance = 0.0
_click_count = 0
_last_click = 0.0

# Phone's raw (un-zeroed) smoothed yaw, and the offset subtracted from it to
# produce state["yaw"]. The phone's quaternion is referenced to its own
# arbitrary/magnetic-north origin, not the robot's facing direction, so a
# zero point must be captured at run start (see /zero_yaw).
_raw_smoothed_yaw = None
_yaw_offset = 0.0

# ── Yaw helpers ───────────────────────────────────────────────────────────────


def quaternion_to_yaw(x, y, z):
    w = math.sqrt(max(0.0, 1.0 - x*x - y*y - z*z))
    yaw = math.atan2(
        2.0 * (w * z + x * y),
        1.0 - 2.0 * (y * y + z * z)
    )
    return math.degrees(yaw)


def angle_diff(a, b):
    return (a - b + 180) % 360 - 180

# ── UDP Listener (phone IMU) ─────────────────────────────────────────────────
# Not started by default anymore -- see imu_yaw_thread() below, which reads the
# board's own LSM6DSV16X gyro instead so the map doesn't depend on a phone.
# Kept for reference / easy revert (swap the thread started in __main__).


def udp_listener():
    global _raw_smoothed_yaw
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.settimeout(1.0)
    print(f"[UDP] Listening on port {UDP_PORT}")

    while True:
        try:
            data, _ = sock.recvfrom(256)
            parts = data.decode().strip().split(",")
            if len(parts) < 3:
                continue
            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
            raw_yaw = quaternion_to_yaw(x, y, z)

            if _raw_smoothed_yaw is None:
                _raw_smoothed_yaw = raw_yaw
            else:
                diff = angle_diff(raw_yaw, _raw_smoothed_yaw)
                _raw_smoothed_yaw = _raw_smoothed_yaw + EMA_ALPHA * diff
                _raw_smoothed_yaw = (_raw_smoothed_yaw + 180) % 360 - 180

            with lock:
                state["yaw"] = round(angle_diff(
                    _raw_smoothed_yaw, _yaw_offset), 2)

        except socket.timeout:
            continue
        except Exception as e:
            print(f"[UDP] Error: {e}")


# ── Onboard IMU gyro (LSM6DSV16X/ISM330DHCX) ─────────────────────────────────
# NOT currently used -- during 257F-DK bring-up this chip did not ACK on
# i2c-1 at 0x6A or 0x6B (see imu_lsm6dsv16x.py header for the full note).
# Kept for reference / easy revert if the hardware issue gets resolved --
# swap the thread started in __main__ back to imu_gyro_yaw_thread.
GYRO_ODR_HZ = 120
GYRO_BIAS_CALIB_SAMPLES = 60
GYRO_BIAS_EMA_ALPHA = 0.02

# Total accel magnitude stays ~1000 mg only when there's no linear
# acceleration, i.e. the board is genuinely still (not just yaw-still).
STATIONARY_ACCEL_MG_LOW = 950
STATIONARY_ACCEL_MG_HIGH = 1050


def imu_gyro_yaw_thread():
    global _raw_smoothed_yaw
    from imu_lsm6dsv16x import LSM6DSV16X

    try:
        imu = LSM6DSV16X()
        if not imu.check_who_am_i():
            print(
                "[IMU] WHO_AM_I mismatch -- wrong I2C_BUS/DEVICE_ADDR? yaw integration disabled")
            return
        imu.configure()
    except Exception as e:
        print(f"[IMU] init failed: {e}")
        return

    print("[IMU] gyro-yaw integration started, calibrating bias...")
    _raw_smoothed_yaw = 0.0

    calib_samples = []
    for _ in range(GYRO_BIAS_CALIB_SAMPLES):
        calib_samples.append(imu.read_gyro_z_dps())
        time.sleep(1.0 / GYRO_ODR_HZ)
    gyro_bias_dps = sum(calib_samples) / len(calib_samples)
    print(f"[IMU] gyro bias = {gyro_bias_dps:.3f} dps")

    last_t = time.time()

    while True:
        try:
            now = time.time()
            dt = now - last_t
            last_t = now

            gyro_z_dps = imu.read_gyro_z_dps()

            # ponytail: the accelerometer can't observe yaw directly (rotating
            # about gravity doesn't change the gravity vector) -- it's used
            # only to detect "no linear acceleration" moments so the gyro's
            # zero-rate bias can be re-tracked continuously, which is what
            # actually stops the slow fake rotation while sitting still.
            ax, ay, az = imu.read_accel_mg()
            accel_mag = math.sqrt(ax * ax + ay * ay + az * az)
            if (STATIONARY_ACCEL_MG_LOW < accel_mag < STATIONARY_ACCEL_MG_HIGH
                    and abs(gyro_z_dps - gyro_bias_dps) < 5):
                gyro_bias_dps += GYRO_BIAS_EMA_ALPHA * \
                    (gyro_z_dps - gyro_bias_dps)

            _raw_smoothed_yaw = (
                _raw_smoothed_yaw + (gyro_z_dps - gyro_bias_dps) * dt + 180) % 360 - 180

            with lock:
                state["yaw"] = round(angle_diff(
                    _raw_smoothed_yaw, _yaw_offset), 2)

            time.sleep(1.0 / GYRO_ODR_HZ)
        except Exception as e:
            print(f"[IMU] Error: {e}")
            time.sleep(0.1)


# ── Onboard magnetometer (IIS2MDC) ───────────────────────────────────────────
# Active yaw source (as of this bring-up) -- confirmed alive on i2c-1 @ 0x1e
# where the gyro didn't respond. Writes into the same shared _raw_smoothed_yaw
# variable udp_listener()/imu_gyro_yaw_thread() would have, so /zero_yaw and
# _raw_input_delta_callback need no changes regardless of which yaw source runs.
#
# Absolute heading straight from Earth's field -- no dead-reckoning drift like
# gyro integration has -- but raw and noisy sample-to-sample, so it's smoothed
# with the same EMA approach as the old phone-UDP source.
# ponytail: no hard-iron/soft-iron calibration and no tilt compensation (the
# STSPIN948 motor drivers + steel chassis nearby can bias the field reading;
# a stray few degrees of constant offset is expected -- use "Zero Heading" to
# correct for it). Add calibration if accuracy needs to improve further.
MAG_ODR_HZ = 100


def imu_mag_yaw_thread():
    global _raw_smoothed_yaw
    from imu_iis2mdc import IIS2MDC

    try:
        mag = IIS2MDC()
        if not mag.check_who_am_i():
            print(
                "[MAG] WHO_AM_I mismatch -- wrong I2C_BUS/DEVICE_ADDR? yaw integration disabled")
            return
        mag.configure()
    except Exception as e:
        print(f"[MAG] init failed: {e}")
        return

    print("[MAG] IIS2MDC magnetometer-yaw integration started")

    while True:
        try:
            mx, my, mz = mag.read_mag_mgauss()
            raw_yaw = math.degrees(math.atan2(my, mx))

            if _raw_smoothed_yaw is None:
                _raw_smoothed_yaw = raw_yaw
            else:
                diff = angle_diff(raw_yaw, _raw_smoothed_yaw)
                _raw_smoothed_yaw = _raw_smoothed_yaw + EMA_ALPHA * diff
                _raw_smoothed_yaw = (_raw_smoothed_yaw + 180) % 360 - 180

            with lock:
                state["yaw"] = round(angle_diff(
                    _raw_smoothed_yaw, _yaw_offset), 2)

            time.sleep(1.0 / MAG_ODR_HZ)
        except Exception as e:
            print(f"[MAG] Error: {e}")
            time.sleep(0.1)


# ── STEVAL-MKBOXPRO gyro over USB (command channel still BLE) ───────────────
# Alternate yaw source: the box's own working LSM6DSV16X gyro, in place of
# either the dead onboard IMU or the magnetometer. Unlike the magnetometer
# this is rate integration (like the onboard gyro thread was), so it needs
# the same startup bias calibration to avoid slow drift while stationary --
# no accelerometer stream wired up here to also gate bias re-tracking
# continuously (ponytail: add if drift over long runs turns out to matter --
# see imu_gyro_yaw_thread's accel-gating for the pattern to copy).
#
# Data comes over USB bulk (not BLE notify) -- see imu_usb_mkbox.py's header
# for why: DATALOG2 firmware only accepts start/stop commands over its BLE
# PnPL channel (direct USB command writes STALL), but once told to stream
# with interface=1 it pushes continuous samples over USB bulk endpoints,
# which is far more robust than BLE notifications for a robot-mounted board
# (no BLE connection to babysit for the actual data path).
USB_GYRO_BIAS_CALIB_SAMPLES = 60
USB_GYRO_POLL_HZ = 200


def imu_usb_yaw_thread():
    global _raw_smoothed_yaw
    import imu_usb_mkbox

    async def run():
        global _raw_smoothed_yaw
        box = imu_usb_mkbox.MkBoxUsbGyro()
        print("[USB-GYRO] connecting over BLE to start USB streaming...")
        await box.start()
        print("[USB-GYRO] streaming started, calibrating bias...")

        calib_samples = []
        gyro_bias_dps = 0.0
        last_t = None
        _raw_smoothed_yaw = 0.0

        while True:
            for gx, gy, gz in box.read_gyro_dps():
                now = time.time()
                if len(calib_samples) < USB_GYRO_BIAS_CALIB_SAMPLES:
                    calib_samples.append(gz)
                    if len(calib_samples) == USB_GYRO_BIAS_CALIB_SAMPLES:
                        gyro_bias_dps = sum(calib_samples) / len(calib_samples)
                        print(f"[USB-GYRO] bias = {gyro_bias_dps:.3f} dps, integration started")
                    last_t = now
                    continue

                dt = now - last_t
                last_t = now
                _raw_smoothed_yaw = (_raw_smoothed_yaw + (gz - gyro_bias_dps) * dt + 180) % 360 - 180
                with lock:
                    state["yaw"] = round(angle_diff(_raw_smoothed_yaw, _yaw_offset), 2)

            await asyncio.sleep(1.0 / USB_GYRO_POLL_HZ)

    while True:
        try:
            asyncio.run(run())
        except Exception as e:
            print(f"[USB-GYRO] Error: {e}")
            time.sleep(2.0)


def _raw_input_delta_callback(raw_dx: int, raw_dy: int):
    """
    Convert mouse movement from robot frame to world frame.
    """

    local_x_cm = raw_dx / COUNTS_PER_CM
    local_y_cm = -raw_dy / COUNTS_PER_CM

    with lock:

        if not state["recording"]:
            return

        yaw_rad = math.radians(state["yaw"] - 90)

        world_dx = (
            local_x_cm * math.cos(yaw_rad)
            - local_y_cm * math.sin(yaw_rad)
        )

        world_dy = (
            local_x_cm * math.sin(yaw_rad)
            + local_y_cm * math.cos(yaw_rad)
        )

        state["x"] += world_dx
        state["y"] += world_dy

        state["distance"] += math.sqrt(
            local_x_cm * local_x_cm +
            local_y_cm * local_y_cm
        )

        path = state["path"]

        if (
            not path
            or math.hypot(
                state["x"] - path[-1][0],
                state["y"] - path[-1][1]
            ) > 0.5
        ):
            path.append([
                round(state["x"], 2),
                round(state["y"], 2)
            ])


def _evdev_thread(device_path: str):
    """
    Read raw input_event structs from the evdev node.
    Accumulates REL_X / REL_Y within each EV_SYN frame, then fires
    the callback once per sync — exactly like a Raw Input report.
    """
    print(f"[evdev] Opening {device_path}")
    try:
        fd = open(device_path, "rb")
    except PermissionError:
        print(
            f"[evdev] Permission denied on {device_path}.\n"
            f"        Fix with:  sudo usermod -aG input $USER\n"
            f"        or run:    sudo chmod a+r {device_path}"
        )
        return
    except FileNotFoundError:
        print(f"[evdev] Device not found: {device_path}")
        return

    pending_dx = 0
    pending_dy = 0
    global _click_count, _last_click
    while True:
        try:
            raw = fd.read(INPUT_EVENT_SIZE)
            if len(raw) < INPUT_EVENT_SIZE:
                # Device disconnected or short read
                print("[evdev] Short read — device disconnected?")
                time.sleep(1.0)
                continue

            _, _, ev_type, ev_code, ev_value = struct.unpack(
                INPUT_EVENT_FMT, raw)

            if ev_type == EV_REL:
                if ev_code == REL_X:
                    pending_dx += ev_value
                elif ev_code == REL_Y:
                    pending_dy += ev_value
            elif ev_type == EV_KEY:

                if ev_code == BTN_LEFT:

                    now = time.time()

                    if ev_value == 1:

                        if now - _last_click < 0.4:
                            _click_count += 1
                        else:
                            _click_count = 1

                        _last_click = now

                        if _click_count >= 2:

                            _click_count = 0

                            with lock:
                                state["x"] = 0.0
                                state["y"] = 0.0
                                state["distance"] = 0.0
                                state["path"] = [[0.0, 0.0]]

                            print("[Mouse] MAP RESET")
                            continue
            elif ev_type == EV_SYN:
                # SYN_REPORT (code 0) marks end of one logical event frame
                if (pending_dx != 0 or pending_dy != 0):
                    _raw_input_delta_callback(pending_dx, pending_dy)
                pending_dx = 0
                pending_dy = 0

        except Exception as e:
            print(f"[evdev] Error: {e}")
            time.sleep(0.1)


# ── Flask Routes ──────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/state")
def get_state():
    with lock:
        return jsonify({
            "x":              round(state["x"], 2),
            "y":              round(state["y"], 2),
            "yaw":            state["yaw"],
            "distance":       round(state["distance"], 2),
            "recording":      state["recording"],
            "path":           state["path"][-500:],
            "counts_per_cm":  COUNTS_PER_CM,
        })


@app.route("/set_counts_per_cm", methods=["POST"])
def set_counts_per_cm():
    """Update the mouse-counts-to-cm calibration factor at runtime (see
    calibrate_linux.py for how to derive an accurate value)."""
    global COUNTS_PER_CM
    try:
        value = float(request.get_json(force=True)["value"])
        if value <= 0:
            raise ValueError
    except Exception:
        return jsonify({"ok": False}), 400
    with lock:
        COUNTS_PER_CM = value
    return jsonify({"ok": True, "counts_per_cm": COUNTS_PER_CM})


@app.route("/set_recording", methods=["POST"])
def set_recording():
    """Set whether odometry accumulates -- driven by main.py based on whether
    the motors are actually commanded to move, since the mouse sensor is
    mounted on the robot itself (nothing to click)."""
    try:
        active = bool(request.get_json(force=True)["active"])
    except Exception:
        return jsonify({"ok": False}), 400
    with lock:
        state["recording"] = active
    return jsonify({"ok": True, "recording": active})


@app.route("/zero_yaw", methods=["POST"])
def zero_yaw():
    """Capture the phone's current raw heading as the new zero-reference,
    so state["yaw"] (and the world_dx/dy rotation in
    _raw_input_delta_callback) aligns with wherever the robot is actually
    facing right now, instead of the phone's own arbitrary yaw origin."""
    global _yaw_offset
    with lock:
        if _raw_smoothed_yaw is not None:
            _yaw_offset = _raw_smoothed_yaw
            state["yaw"] = 0.0
        return jsonify({"ok": _raw_smoothed_yaw is not None, "yaw_offset": round(_yaw_offset, 2)})


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    t_yaw = threading.Thread(
        target=imu_ble_yaw_thread,
        daemon=True
    )
    t_yaw.start()

    device_path = "/dev/input/event1"
    print("Using:", device_path)

    t_mouse = threading.Thread(
        target=_evdev_thread,
        args=(device_path,),
        daemon=True
    )
    t_mouse.start()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True
    )
