# server.py  ── Linux / OpenSTLinux version (STM32MP257F-DK)
import asyncio
import json
import math
import os
import struct
import threading
import time
from flask import Flask, jsonify, request, send_from_directory

# ── Constants ─────────────────────────────────────────────────────────────────
COUNTS_PER_CM = 25   # default only -- overridden by odometry_config.json (see
                     # _load_odom_config; calibrate with calibrate_linux.py)

# Trail limits: the server appends a path point every 0.5 cm of travel; /state
# used to send just the last 500 (2.5 m!) so long drives visibly lost their
# tail. Now the full trail is kept (thinned 2:1 above PATH_MAX_POINTS to bound
# memory) and /state decimates evenly to PATH_SEND_MAX points, always keeping
# the newest point -- the trail never disappears, the payload stays bounded.
PATH_MAX_POINTS = 20000
PATH_SEND_MAX = 1000

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

_click_count = 0
_last_click = 0.0

# Runtime settings persisted across restarts (currently just counts_per_cm --
# fixes "Set" appearing to work then snapping back to 25 on the next launch).
_ODOM_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "odometry_config.json")


def _load_odom_config():
    try:
        with open(_ODOM_CONFIG_PATH) as f:
            cfg = json.load(f)
        cpc = float(cfg["counts_per_cm"])
        if cpc > 0:
            state["counts_per_cm"] = cpc
            print(f"[CONFIG] counts_per_cm = {cpc}")
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        pass


def _save_odom_config():
    try:
        with open(_ODOM_CONFIG_PATH, "w") as f:
            json.dump({"counts_per_cm": state["counts_per_cm"]}, f)
    except OSError as e:
        print(f"[CONFIG] save failed: {e}")

# Fused raw (un-zeroed) yaw from the gyro+mag complementary filter, and the
# offset subtracted from it to produce state["yaw"]. The mag heading is
# referenced to magnetic north, not the robot's facing direction, so a zero
# point is captured at run start / on demand (see /zero_yaw).
_raw_smoothed_yaw = None
_yaw_offset = 0.0

# ── Yaw helpers ───────────────────────────────────────────────────────────────


def angle_diff(a, b):
    return (a - b + 180) % 360 - 180


# ── Onboard magnetometer (IIS2MDC) ───────────────────────────────────────────
# The RBT01 exposes ONLY the magnetometer (i2c-1 @ 0x1e) and a pressure sensor
# (0x5d) -- confirmed by `i2cdetect -y 1`. There is no onboard accel/gyro, so
# those come from the STEVAL-MKBOXPRO over USB (see imu_usb_mkbox.py). Gyro and
# mag therefore live on two physically separate boards; only their shared
# vertical axis (yaw) is fused -- see imu_fusion_yaw_thread.
MAG_ODR_HZ = 100
USB_GYRO_POLL_HZ = 200

# Complementary-filter mag-correction time constants (seconds). Each cycle the
# gyro-integrated yaw is pulled toward the calibrated mag heading by
# w = 1 - exp(-dt/tau), so the trust is rate-independent (the loop rate floats
# with USB timing -- a fixed per-cycle weight would change strength with data
# rate). Moving: long tau so the (motor-field-biased) mag only trims slow gyro
# drift. At rest: short tau so yaw locks to absolute heading and residual gyro
# bias can't creep. ponytail: these two taus are the tuning knobs the hardware
# needs -- raise TAU_MAG_MOVING if driving near the motors bends the heading,
# lower it if yaw drifts during long drives.
TAU_MAG_MOVING = 5.0
TAU_MAG_REST = 0.7

# Below this |bias-corrected gyro rate| (dps), with accel ≈ 1g, the robot is
# treated as stationary (selects TAU_MAG_REST + gyro-bias re-tracking).
STATIONARY_GYRO_DPS = 2.0

# Mag-only fallback smoothing (EMA per 100 Hz sample) used whenever the fusion
# loop isn't publishing (box off/unplugged, BLE scan, gyro-bias calibration) --
# absolute heading with no gyro smoothing. Measured on this unit: raw
# calibrated-heading sigma ~0.9 deg -> EMA 0.1 leaves ~0.2 deg jitter.
MAG_ONLY_EMA = 0.1
MAG_ONLY_RETRY_S = 30.0     # wait this long between MKBOXPRO reconnect attempts
FUSION_STALE_S = 0.5        # watchdog takes over yaw after this publish gap

_MAG_CALIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "mag_calib.json")

# Hard/soft-iron correction, loaded from mag_calib.json (or identity until a
# calibration spin runs). offset = hard-iron center; scale = soft-iron X/Y gain.
_mag_calib = {"offset": [0.0, 0.0], "scale": [1.0, 1.0]}
_latest_mag = None        # raw (mx,my,mz) mgauss, set by _mag_reader_thread
_mag_collecting = False   # True while a calibration spin is gathering samples
_mag_samples = []         # (mx,my) accumulated during a calibration spin

# Fusion internals exposed on /debug_yaw so gyro-vs-mag disagreement (sign
# flips, scale errors, mag disturbance) is observable instead of guessed at.
_debug = {"gyro_yaw": None, "mag_heading": None, "gyro_bias": None,
          "stationary": None, "gz_last": None}


def _load_mag_calib():
    global _mag_calib
    try:
        with open(_MAG_CALIB_PATH) as f:
            data = json.load(f)
        _mag_calib = {"offset": [float(data["offset"][0]), float(data["offset"][1])],
                      "scale": [float(data["scale"][0]), float(data["scale"][1])]}
        print(f"[MAG-CAL] loaded {_mag_calib}")
        return True
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return False


def _fit_mag_calib(samples):
    """Hard+soft-iron fit on X/Y (all yaw needs). Hard-iron = per-axis
    (min+max)/2 center; soft-iron = per-axis avg_radius/axis_radius gain,
    turning the field-vector ellipse back into a circle. ponytail: X/Y only,
    no Z and no tilt compensation -- correct for a level rover; upgrade to a
    full 3D ellipsoid fit + accel tilt-comp if it ever drives on slopes."""
    xs = [s[0] for s in samples]
    ys = [s[1] for s in samples]
    ox = (min(xs) + max(xs)) / 2.0
    oy = (min(ys) + max(ys)) / 2.0
    rx = (max(xs) - min(xs)) / 2.0 or 1.0
    ry = (max(ys) - min(ys)) / 2.0 or 1.0
    r_avg = (rx + ry) / 2.0
    return {"offset": [ox, oy], "scale": [r_avg / rx, r_avg / ry]}


def _apply_mag_calib(mx, my):
    ox, oy = _mag_calib["offset"]
    sx, sy = _mag_calib["scale"]
    return (mx - ox) * sx, (my - oy) * sy


def _mag_heading_deg():
    """Calibrated absolute heading from the latest mag reading, or None."""
    if _latest_mag is None:
        return None
    mxc, myc = _apply_mag_calib(_latest_mag[0], _latest_mag[1])
    return math.degrees(math.atan2(myc, mxc))


def _mag_reader_thread():
    """Read IIS2MDC and publish raw (mx,my,mz); feed the calibration collector
    when a spin is active."""
    global _latest_mag
    from imu_iis2mdc import IIS2MDC

    try:
        mag = IIS2MDC()
        if not mag.check_who_am_i():
            print("[MAG] WHO_AM_I mismatch -- magnetometer correction disabled")
            return
        mag.configure()
    except Exception as e:
        print(f"[MAG] init failed: {e}")
        return

    print("[MAG] IIS2MDC reader started")
    while True:
        try:
            mx, my, mz = mag.read_mag_mgauss()
            _latest_mag = (mx, my, mz)
            if _mag_collecting:
                _mag_samples.append((mx, my))
            time.sleep(1.0 / MAG_ODR_HZ)
        except Exception as e:
            print(f"[MAG] Error: {e}")
            time.sleep(0.1)


async def _run_mag_calibration_spin():
    """Trigger the robot's warmup spin and collect mag samples during it, then
    fit + persist the hard/soft-iron correction. Returns True on success."""
    global _mag_collecting, _mag_samples, _mag_calib
    import ssl
    import urllib.request

    _mag_samples = []
    _mag_collecting = True
    print("[MAG-CAL] spin starting, collecting samples...")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            "https://127.0.0.1:8000/calibrate_rotate", method="POST")
        with urllib.request.urlopen(req, timeout=1, context=ctx):
            pass
    except Exception as e:
        print(f"[MAG-CAL] spin request failed: {e}")

    await asyncio.sleep(11.0)   # matches /calibrate_rotate's ~10 s left+right spin
    _mag_collecting = False

    if len(_mag_samples) < 20:
        print(f"[MAG-CAL] too few samples ({len(_mag_samples)}); keeping identity calib")
        return False

    _mag_calib = _fit_mag_calib(_mag_samples)
    try:
        with open(_MAG_CALIB_PATH, "w") as f:
            json.dump(_mag_calib, f)
        print(f"[MAG-CAL] fitted + saved {_mag_calib} ({len(_mag_samples)} samples)")
    except OSError as e:
        print(f"[MAG-CAL] save failed: {e}")
    return True


_last_fusion_pub = 0.0  # time.time() of the fusion loop's last yaw publish


def _mag_watchdog_thread():
    """Publish smoothed mag-only yaw whenever the fusion loop goes quiet
    (box off/unplugged, BLE scan in progress, gyro-bias calibration). Absolute
    heading with no gyro smoothing -- keeps the map usable instead of leaving
    yaw frozen. Backs off automatically the moment fusion publishes again."""
    global _raw_smoothed_yaw
    while True:
        if time.time() - _last_fusion_pub > FUSION_STALE_S:
            heading = _mag_heading_deg()
            if heading is not None:
                if _raw_smoothed_yaw is None:
                    _raw_smoothed_yaw = heading
                else:
                    _raw_smoothed_yaw = (_raw_smoothed_yaw + MAG_ONLY_EMA *
                                         angle_diff(heading, _raw_smoothed_yaw)
                                         + 180) % 360 - 180
                with lock:
                    state["yaw"] = round(angle_diff(
                        _raw_smoothed_yaw, _yaw_offset), 2)
        time.sleep(1.0 / MAG_ODR_HZ)


def imu_fusion_yaw_thread():
    """Yaw-only complementary filter: MKBOXPRO gyro-Z (USB) integrated for smooth
    short-term rate, corrected toward the calibrated IIS2MDC magnetic heading
    (I2C) for absolute, drift-free heading. Gyro and mag sit on two separate
    boards, so only the shared vertical (yaw) axis is fused -- no full 9-DOF
    attitude, which would (wrongly) assume one common body frame.
    If the box is unreachable (off/unplugged), degrades to mag-only yaw and
    retries the box every MAG_ONLY_RETRY_S."""
    global _raw_smoothed_yaw
    import imu_usb_mkbox

    threading.Thread(target=_mag_reader_thread, daemon=True).start()
    _load_mag_calib()
    threading.Thread(target=_mag_watchdog_thread, daemon=True).start()

    async def run():
        global _raw_smoothed_yaw, _last_fusion_pub
        box = imu_usb_mkbox.MkBoxUsbGyro()
        print("[FUSION] connecting over BLE to start USB streaming (gyro+accel)...")
        await box.start()
        print("[FUSION] streaming started, waiting for first mag reading...")

        while _latest_mag is None:
            await asyncio.sleep(0.1)

        # First-ever run (no cached calib): spin to fit hard/soft-iron. Later
        # runs reuse mag_calib.json and skip straight to gyro-bias calibration.
        if _mag_calib["scale"] == [1.0, 1.0] and _mag_calib["offset"] == [0.0, 0.0]:
            await _run_mag_calibration_spin()
        else:
            print("[FUSION] using cached mag calibration; warming up gyro...")
            await asyncio.sleep(2.0)

        # Flush any samples buffered during the spin/warmup.
        for _ in range(30):
            box.read_gyro_dps()
            box.read_accel_mg()
            await asyncio.sleep(0.02)

        # ── Gyro bias calibration (2 s stationary) ──
        print("[FUSION] calibrating gyro bias (keep robot still)...")
        bias_samples = []
        cal_deadline = time.time() + 2.0
        while time.time() < cal_deadline:
            gyro_batch, _ = box.read_gyro_and_accel()
            for gx, gy, gz in gyro_batch:
                bias_samples.append(gz)
            await asyncio.sleep(0.05)
        gyro_bias = sum(bias_samples) / len(bias_samples) if bias_samples else 0.0
        print(f"[FUSION] gyro bias = {gyro_bias:.3f} dps ({len(bias_samples)} samples)")

        # ── Bootstrap yaw from absolute mag heading ──
        yaw = _mag_heading_deg()
        if yaw is None:
            yaw = 0.0
        _raw_smoothed_yaw = yaw
        print(f"[FUSION] initial yaw from mag: {yaw:.1f} deg")
        print("[FUSION] complementary gyro+mag fusion started")

        last_t = time.time()
        cycle_prev = None
        while True:
            gyro_batch, accel_batch = box.read_gyro_and_accel()
            now = time.time()

            if not gyro_batch:
                await asyncio.sleep(1.0 / USB_GYRO_POLL_HZ)
                continue

            dt_per_sample = (now - last_t) / len(gyro_batch)
            last_t = now

            # ── Gyro integration (fast path) ──
            stationary = True
            for gx, gy, gz in gyro_batch:
                gz_corrected = gz - gyro_bias
                # ponytail: gz sign assumed = CCW-positive yaw rate. If the HUD
                # turns the wrong way, negate here (axis order unverified -- see
                # imu_usb_mkbox.py header).
                yaw = (yaw + gz_corrected * dt_per_sample + 180) % 360 - 180

                ax_mg, ay_mg, az_mg = accel_batch[-1] if accel_batch else (1000.0, 0.0, 0.0)
                accel_mag = math.sqrt(ax_mg**2 + ay_mg**2 + az_mg**2)
                at_rest = 950 < accel_mag < 1050 and abs(gz_corrected) < STATIONARY_GYRO_DPS
                if not at_rest:
                    stationary = False
                # Track gyro bias whenever genuinely still (any mode).
                if at_rest:
                    gyro_bias += 0.01 * (gz - gyro_bias)

            # ── Mag correction (absolute heading) ──
            # At rest, short tau locks yaw to the mag so residual gyro-bias
            # creep can't accumulate -- this is what stops the slow settling
            # drift while parked. Moving, long tau lets the gyro dominate and
            # the mag only trims slow drift. exp() makes the pull strength
            # independent of the (jittery) USB batch rate.
            mag_heading = _mag_heading_deg()
            if mag_heading is not None:
                cycle_dt = now - cycle_prev if cycle_prev else 0.005
                tau = TAU_MAG_REST if stationary else TAU_MAG_MOVING
                w = 1.0 - math.exp(-cycle_dt / tau)
                yaw = (yaw + w * angle_diff(mag_heading, yaw) + 180) % 360 - 180
            cycle_prev = now

            _raw_smoothed_yaw = yaw
            _last_fusion_pub = time.time()
            with lock:
                state["yaw"] = round(angle_diff(yaw, _yaw_offset), 2)

            await asyncio.sleep(1.0 / USB_GYRO_POLL_HZ)

    while True:
        try:
            asyncio.run(run())
        except Exception as e:
            print(f"[FUSION] Error: {e} -- watchdog serves mag-only yaw; "
                  f"retrying the box in {MAG_ONLY_RETRY_S:.0f}s")
            time.sleep(MAG_ONLY_RETRY_S)


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
            # Bound memory on very long runs by halving resolution, never by
            # dropping the tail (that's what made the trail disappear before).
            if len(path) > PATH_MAX_POINTS:
                state["path"] = path[::2]


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
        path = state["path"]
        if len(path) > PATH_SEND_MAX:
            # Decimate evenly across the WHOLE trail (never truncate the old
            # end -- that's what made long trails vanish), keeping the newest
            # point exact so the line always reaches the car.
            step = len(path) / (PATH_SEND_MAX - 1)
            path = [path[int(i * step)] for i in range(PATH_SEND_MAX - 1)] + [path[-1]]
        return jsonify({
            "x":              round(state["x"], 2),
            "y":              round(state["y"], 2),
            "yaw":            state["yaw"],
            "distance":       round(state["distance"], 2),
            "recording":      state["recording"],
            "path":           path,
            "counts_per_cm":  state["counts_per_cm"],
        })


@app.route("/set_counts_per_cm", methods=["POST"])
def set_counts_per_cm():
    """Update the mouse-counts-to-cm calibration factor at runtime (see
    calibrate_linux.py for how to derive an accurate value). Persisted to
    odometry_config.json so it survives restarts."""
    try:
        value = float(request.get_json(force=True)["value"])
        if value <= 0:
            raise ValueError
    except Exception:
        return jsonify({"ok": False}), 400
    with lock:
        state["counts_per_cm"] = value
    _save_odom_config()
    return jsonify({"ok": True, "counts_per_cm": value})


@app.route("/reset_map", methods=["POST"])
def reset_map():
    """Clear position, distance, and trail (same as double-clicking the mouse
    button, but reachable from the web UI)."""
    with lock:
        state["x"] = 0.0
        state["y"] = 0.0
        state["distance"] = 0.0
        state["path"] = [[0.0, 0.0]]
    return jsonify({"ok": True})


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


@app.route("/recalibrate_mag", methods=["POST"])
def recalibrate_mag():
    """Drop the cached mag calibration and re-run the spin+fit -- use after
    moving to a new environment where the ambient/ferrous field differs. The
    fusion thread owns the actual spin (it holds the USB/gyro loop), so we just
    delete the cache and signal it; the next filter cycle picks up the change.
    ponytail: deletes the file and resets to identity so the running thread
    re-fits on its own next bootstrap -- simplest reliable trigger without
    cross-thread asyncio plumbing."""
    global _mag_calib
    try:
        os.remove(_MAG_CALIB_PATH)
    except FileNotFoundError:
        pass
    _mag_calib = {"offset": [0.0, 0.0], "scale": [1.0, 1.0]}

    async def _spin():
        await _run_mag_calibration_spin()
    threading.Thread(
        target=lambda: asyncio.run(_spin()), daemon=True).start()
    return jsonify({"ok": True})


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _load_odom_config()

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
