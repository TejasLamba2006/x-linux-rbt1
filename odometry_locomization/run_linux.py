# server.py  ── Linux / OpenSTLinux version (STM32MP257F-DK)
import asyncio
import json
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
    "counts_per_cm": COUNTS_PER_CM,
}

_raw_dx_buf = deque(maxlen=SMOOTHING_WIN)
_ema_distance = 0.0
_click_count = 0
_last_click = 0.0
_last_mouse_move_time = 0.0  # monotonic time of last REL_X/REL_Y event

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
USB_GYRO_POLL_HZ = 200


# ── Fusion: Madgwick AHRS — gyro + accel + mag 9-DOF fusion ─────────────────
# Replaces the old hand-rolled complementary filter with a proper Madgwick
# gradient-descent AHRS filter.  The filter fuses:
#   - Gyro (MKBOXPRO USB): smooth short-term angular rate
#   - Accel (MKBOXPRO USB): gravity reference for tilt compensation
#   - Mag  (IIS2MDC I2C):  absolute heading reference
# The Madgwick filter outputs a quaternion; yaw is extracted from it with
# proper tilt compensation — no more raw atan2(mx,my) that assumes a
# perfectly level sensor.
#
# gyro_bias: running EMA of gyro_z when stationary (accel magnitude ≈ 1g).
# The filter's gyro input is bias-corrected each sample.
# When state["recording"] is False, yaw is frozen (no integration).

_latest_mag = None  # (mx, my, mz) in milligauss, set by _mag_reader_thread


class _MadgwickAHRS:
    """Madgwick AHRS filter (gradient-descent, 9-DOF).
    Quaternion order: [w, x, y, z]."""

    def __init__(self, beta=0.1):
        self.q = [1.0, 0.0, 0.0, 0.0]
        self.beta = beta  # filter gain (0.01–0.5; higher = more trust in accel/mag)

    def _inv_sqrt(self, x):
        return x ** -0.5 if x > 0 else 1.0

    def update(self, gx, gy, gz, ax, ay, az, mx, my, mz, dt):
        """Update with gyro (dps), accel (mg), mag (mgauss), dt (s).
        Standard Madgwick AHRS 9-DOF gradient-descent algorithm."""
        q0, q1, q2, q3 = self.q

        # Convert gyro from dps to rad/s
        gx_r, gy_r, gz_r = math.radians(gx), math.radians(gy), math.radians(gz)

        # Normalise accel
        norm_a = math.sqrt(ax * ax + ay * ay + az * az)
        if norm_a < 1e-6:
            return
        ax_n, ay_n, az_n = ax / norm_a, ay / norm_a, az / norm_a

        # Normalise mag
        norm_m = math.sqrt(mx * mx + my * my + mz * mz)
        if norm_m < 1e-6:
            return
        mx_n, my_n, mz_n = mx / norm_m, my / norm_m, mz / norm_m

        # Auxiliary variables (reused for efficiency)
        _2q0 = 2.0 * q0
        _2q1 = 2.0 * q1
        _2q2 = 2.0 * q2
        _2q3 = 2.0 * q3
        _2q0q2 = 2.0 * q0 * q2
        _2q2q3 = 2.0 * q2 * q3
        q0q0 = q0 * q0
        q0q1 = q0 * q1
        q0q2 = q0 * q2
        q0q3 = q0 * q3
        q1q1 = q1 * q1
        q1q2 = q1 * q2
        q1q3 = q1 * q3
        q2q2 = q2 * q2
        q2q3 = q2 * q3
        q3q3 = q3 * q3

        # Reference direction of Earth's magnetic field
        hx = mx_n * q0q0 - _2q0 * my_n * q3 + _2q0 * mz_n * q2 + mx_n * q1q1 + _2q1 * my_n * q2 + _2q1 * mz_n * q3 - mx_n * q2q2 - mx_n * q3q3
        hy = _2q0 * mx_n * q3 + my_n * q0q0 - _2q0 * mz_n * q1 + _2q1 * mx_n * q2 - my_n * q1q1 + my_n * q2q2 - _2q2 * mz_n * q3 + my_n * q3q3
        _2bx = math.sqrt(hx * hx + hy * hy)
        _2bz = -_2q0 * mx_n * q2 + _2q0 * my_n * q1 + mz_n * q0q0 + _2q1 * mx_n * q3 - mz_n * q1q1 + _2q2 * my_n * q3 - mz_n * q2q2 + mz_n * q3q3

        # Gradient descent corrective step (Madgwick Eq. 32)
        s0 = -_2q2 * (2.0 * q1q3 - _2q0q2 - ax_n) + _2q1 * (2.0 * q0q1 + _2q2q3 - az_n) - _2bx * q2 * (_2bx * (0.5 - q2q2 - q3q3) + _2bz * (q1q3 - q0q2) - mx_n) + (-_2bx * q3 + _2bz * q1) * (_2bx * (q1q2 - q0q3) + _2bz * (q0q1 + q2q3) - my_n) + _2bx * q2 * (_2bx * (q0q2 + q1q3) + _2bz * (0.5 - q1q1 - q2q2) - mz_n) + (_2bx * q1 + _2bz * q0) * (_2bx * (q0q3 + q1q2) + _2bz * (q2q3 - q0q1) - mz_n)
        s1 = _2q3 * (2.0 * q1q3 - _2q0q2 - ax_n) + _2q0 * (2.0 * q0q1 + _2q2q3 - az_n) - 4.0 * q1 * (1.0 - 2.0 * q1q1 - 2.0 * q2q2 - az_n) + _2bz * q0 * (_2bx * (0.5 - q2q2 - q3q3) + _2bz * (q1q3 - q0q2) - mx_n) + _2bz * q2 * (_2bx * (q1q2 - q0q3) + _2bz * (q0q1 + q2q3) - my_n) + (_2bx * q3 + _2bz * q1) * (_2bx * (q0q2 + q1q3) + _2bz * (0.5 - q1q1 - q2q2) - mz_n) + (_2bx * q0 - _2bz * q2) * (_2bx * (q0q3 + q1q2) + _2bz * (q2q3 - q0q1) - mz_n)
        s2 = -_2q0 * (2.0 * q1q3 - _2q0q2 - ax_n) + _2q3 * (2.0 * q0q1 + _2q2q3 - az_n) - 4.0 * q2 * (1.0 - 2.0 * q1q1 - 2.0 * q2q2 - az_n) + (-_2bx * q1 + _2bz * q0) * (_2bx * (0.5 - q2q2 - q3q3) + _2bz * (q1q3 - q0q2) - mx_n) + (_2bx * q2 + _2bz * q3) * (_2bx * (q1q2 - q0q3) + _2bz * (q0q1 + q2q3) - my_n) + (_2bx * q1 + _2bz * q0) * (_2bx * (q0q2 + q1q3) + _2bz * (0.5 - q1q1 - q2q2) - mz_n) + (_2bx * q3 - _2bz * q1) * (_2bx * (q0q3 + q1q2) + _2bz * (q2q3 - q0q1) - mz_n)
        s3 = _2q1 * (2.0 * q1q3 - _2q0q2 - ax_n) + _2q2 * (2.0 * q0q1 + _2q2q3 - az_n) + (-_2bx * q0 + _2bz * q2) * (_2bx * (0.5 - q2q2 - q3q3) + _2bz * (q1q3 - q0q2) - mx_n) + (-_2bx * q3 - _2bz * q1) * (_2bx * (q1q2 - q0q3) + _2bz * (q0q1 + q2q3) - my_n) + (-_2bx * q2 + _2bz * q3) * (_2bx * (q0q2 + q1q3) + _2bz * (0.5 - q1q1 - q2q2) - mz_n) + (_2bx * q0 + _2bz * q2) * (_2bx * (q0q3 + q1q2) + _2bz * (q2q3 - q0q1) - mz_n)

        # Normalise step
        norm_s = math.sqrt(s0 * s0 + s1 * s1 + s2 * s2 + s3 * s3)
        if norm_s < 1e-6:
            return
        s0 /= norm_s
        s1 /= norm_s
        s2 /= norm_s
        s3 /= norm_s

        # Rate of change of quaternion from gyroscope + corrective term
        qDot0 = 0.5 * (-q1 * gx_r - q2 * gy_r - q3 * gz_r) - self.beta * s0
        qDot1 = 0.5 * (q0 * gx_r + q2 * gz_r - q3 * gy_r) - self.beta * s1
        qDot2 = 0.5 * (q0 * gy_r - q1 * gz_r + q3 * gx_r) - self.beta * s2
        qDot3 = 0.5 * (q0 * gz_r + q1 * gy_r - q2 * gx_r) - self.beta * s3

        # Integrate
        q0 += qDot0 * dt
        q1 += qDot1 * dt
        q2 += qDot2 * dt
        q3 += qDot3 * dt

        # Normalise
        norm_q = math.sqrt(q0 * q0 + q1 * q1 + q2 * q2 + q3 * q3)
        self.q = [q0 / norm_q, q1 / norm_q, q2 / norm_q, q3 / norm_q]

    def update_gyro_only(self, gx, gy, gz, dt):
        """Gyro-only update (no accel/mag) — used when accel/mag unavailable."""
        q0, q1, q2, q3 = self.q
        gx_r, gy_r, gz_r = math.radians(gx), math.radians(gy), math.radians(gz)
        q0 += 0.5 * (-q1 * gx_r - q2 * gy_r - q3 * gz_r) * dt
        q1 += 0.5 * (q0 * gx_r + q2 * gz_r - q3 * gy_r) * dt
        q2 += 0.5 * (q0 * gy_r - q1 * gz_r + q3 * gx_r) * dt
        q3 += 0.5 * (q0 * gz_r + q1 * gy_r - q2 * gx_r) * dt
        norm_q = math.sqrt(q0 * q0 + q1 * q1 + q2 * q2 + q3 * q3)
        self.q = [q0 / norm_q, q1 / norm_q, q2 / norm_q, q3 / norm_q]

    def yaw_degrees(self):
        """Extract yaw (Z-axis rotation) from quaternion in degrees [-180, 180)."""
        q0, q1, q2, q3 = self.q
        yaw = math.degrees(math.atan2(2.0 * (q0 * q3 + q1 * q2),
                                      1.0 - 2.0 * (q2 * q2 + q3 * q3)))
        return yaw


def _mag_reader_thread():
    """Read IIS2MDC magnetometer and publish raw (mx,my,mz) for the fusion filter."""
    global _latest_mag
    from imu_iis2mdc import IIS2MDC

    try:
        mag = IIS2MDC()
        if not mag.check_who_am_i():
            print("[FUSION-MAG] WHO_AM_I mismatch -- magnetometer correction disabled")
            return
        mag.configure()
    except Exception as e:
        print(f"[FUSION-MAG] init failed: {e}")
        return

    print("[FUSION-MAG] magnetometer reader started")
    while True:
        try:
            mx, my, mz = mag.read_mag_mgauss()
            _latest_mag = (mx, my, mz)
            time.sleep(1.0 / MAG_ODR_HZ)
        except Exception as e:
            print(f"[FUSION-MAG] Error: {e}")
            time.sleep(0.1)


def imu_fusion_yaw_thread():
    global _raw_smoothed_yaw
    import imu_usb_mkbox

    threading.Thread(target=_mag_reader_thread, daemon=True).start()

    async def run():
        global _raw_smoothed_yaw
        box = imu_usb_mkbox.MkBoxUsbGyro()
        print("[FUSION] connecting over BLE to start USB streaming (gyro+accel)...")
        await box.start()
        print("[FUSION] streaming started, waiting for first mag reading...")

        while _latest_mag is None:
            await asyncio.sleep(0.1)

        # ── Warmup rotation ──
        print("[FUSION] requesting warmup rotation...")
        try:
            import urllib.request
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request("https://127.0.0.1:8000/calibrate_rotate",
                                        method="POST")
            with urllib.request.urlopen(req, timeout=1, context=ctx) as resp:
                print(f"[FUSION] warmup rotation started ({resp.read().decode()})")
        except Exception as e:
            print(f"[FUSION] warmup rotation request failed: {e}")

        await asyncio.sleep(11.0)
        for _ in range(30):
            box.read_gyro_dps()
            box.read_accel_mg()
            await asyncio.sleep(0.02)

        # ── Gyro bias calibration (2 s stationary) ──
        print("[FUSION] warmup done, calibrating gyro bias (keep robot still)...")
        bias_samples = []
        cal_deadline = time.time() + 2.0
        while time.time() < cal_deadline:
            gyro_batch, _ = box.read_gyro_and_accel()
            for gx, gy, gz in gyro_batch:
                bias_samples.append(gz)
            await asyncio.sleep(0.05)
        gyro_bias = sum(bias_samples) / len(bias_samples) if bias_samples else 0.0
        print(f"[FUSION] gyro bias = {gyro_bias:.3f} dps ({len(bias_samples)} samples)")

        # ── Init Madgwick filter ──
        ahrs = _MadgwickAHRS(beta=0.1)

        # Bootstrap: set initial orientation from mag + accel
        mx, my, mz = _latest_mag
        ax, ay, az = 1000.0, 0.0, 0.0  # assume roughly level
        ahrs.update(0, 0, 0, ax, ay, az, mx, my, mz, 0.1)
        _raw_smoothed_yaw = ahrs.yaw_degrees()
        print(f"[FUSION] initial yaw from mag: {_raw_smoothed_yaw:.1f} deg")
        print("[FUSION] Madgwick 9-DOF fusion started")

        last_t = time.time()
        while True:
            gyro_batch, accel_batch = box.read_gyro_and_accel()
            now = time.time()

            if not gyro_batch:
                await asyncio.sleep(1.0 / USB_GYRO_POLL_HZ)
                continue

            # Process each gyro sample; pair with latest accel sample
            dt_per_sample = (now - last_t) / len(gyro_batch) if gyro_batch else 1.0 / USB_GYRO_POLL_HZ
            last_t = now

            for gx, gy, gz in gyro_batch:
                dt = dt_per_sample

                # Bias correction
                gz_corrected = gz - gyro_bias

                # Get accel sample (use last available)
                ax_mg, ay_mg, az_mg = accel_batch[-1] if accel_batch else (1000.0, 0.0, 0.0)

                # Get mag sample (may be None if mag reader hasn't delivered yet)
                if _latest_mag is not None:
                    mx_mg, my_mg, mz_mg = _latest_mag
                else:
                    mx_mg, my_mg, mz_mg = 0.0, 1.0, 0.0  # fallback: assume north

                if state["recording"]:
                    # Full 9-DOF update
                    ahrs.update(gx, gy, gz_corrected,
                                ax_mg, ay_mg, az_mg,
                                mx_mg, my_mg, mz_mg, dt)
                    _raw_smoothed_yaw = ahrs.yaw_degrees()
                else:
                    # When idle: only track gyro bias, don't update yaw
                    accel_mag = math.sqrt(ax_mg**2 + ay_mg**2 + az_mg**2)
                    if 950 < accel_mag < 1050 and abs(gz_corrected) < 5:
                        gyro_bias += 0.01 * (gz - gyro_bias)

            with lock:
                state["yaw"] = round(angle_diff(
                    _raw_smoothed_yaw, _yaw_offset), 2)

            await asyncio.sleep(1.0 / USB_GYRO_POLL_HZ)

    while True:
        try:
            asyncio.run(run())
        except Exception as e:
            print(f"[FUSION] Error: {e}")
            time.sleep(2.0)


def _raw_input_delta_callback(raw_dx: int, raw_dy: int):
    """
    Convert mouse movement from robot frame to world frame.
    """

    local_x_cm = raw_dx / state["counts_per_cm"]
    local_y_cm = -raw_dy / state["counts_per_cm"]

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
                _last_mouse_move_time = time.time()
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
            "counts_per_cm":  state["counts_per_cm"],
        })


@app.route("/set_counts_per_cm", methods=["POST"])
def set_counts_per_cm():
    """Update the mouse-counts-to-cm calibration factor at runtime (see
    calibrate_linux.py for how to derive an accurate value)."""
    try:
        value = float(request.get_json(force=True)["value"])
        if value <= 0:
            raise ValueError
    except Exception:
        return jsonify({"ok": False}), 400
    with lock:
        state["counts_per_cm"] = value
    return jsonify({"ok": True, "counts_per_cm": value})


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
        target=imu_fusion_yaw_thread,
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
