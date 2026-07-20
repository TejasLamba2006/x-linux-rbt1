"""
marker_vision.py — ArUco marker detection + drive-to-marker autopilot.

Sees an ArUco marker through a USB webcam, measures its distance and bearing
using the pinhole camera model (we know the marker's real size), then drives
the robot up to the marker and stops at a standoff distance.

Self-contained: the only coupling to the rest of the app is the three
callables handed to MarkerNavigator.start() -- the drive module, a ToF
distance reader, and a status callback. Imported lazily by main.py; if OpenCV
(cv2) isn't installed, CV_AVAILABLE stays False and vision silently disables,
exactly like the voice/ToF/odometry features.

MATH (no full camera calibration needed):
    distance_mm = marker_size_mm * focal_px / marker_pixel_width
    bearing_deg = degrees(atan2(cx - W/2, focal_px))
where marker_pixel_width is the mean of the two horizontal marker sides (tilt-
resistant) and cx is the marker centre. focal_px is the one value that MUST be
measured on hardware (see calibrate() / __main__), but ships with a usable
default and is backstopped by the ToF cross-check.

HARDWARE-TUNE LIST (config keys under "vision" in robot_config.json):
    focal_px            per camera+resolution -- run __main__ once to capture
    rotate_floor / throttle_floor   motor stall speeds -- raise until wheels move
    kw / kv             control gains -- halve if it oscillates

ponytail: monocular ratio + P-control, no solvePnP pose / no PID. Upgrade to
cv2.solvePnP with a chessboard-calibrated camera matrix only if you later need
docking-precision lateral alignment; drive-and-stop doesn't.
"""

import logging
import math
import threading
import time

import numpy as np  # hard dep on the board (ONNX voice too); safe at module level

logger = logging.getLogger(__name__)

CV_AVAILABLE = False
try:
    import cv2
    CV_AVAILABLE = True
except Exception as e:  # pragma: no cover - depends on board deps
    logging.getLogger(__name__).warning(f"Marker vision unavailable (cv2 not loaded): {e}")


# Defaults for every tunable. main.py merges robot_config.json["vision"] over this.
DEFAULT_CONFIG = {
    "camera": 0,            # cv2.VideoCapture source: int index or "/dev/videoN" path
    "frame_width": 1280,
    "frame_height": 720,
    "marker_size_mm": 100.0,
    "focal_px": 900.0,      # MUST calibrate per camera/res; default ~ 1280px @ 60-70deg HFOV
    "standoff_mm": 400.0,   # stop this far from the marker
    "target_marker_id": None,  # None = lock onto the nearest (largest) marker
    "kw": 2.5,              # rotate command per degree of bearing error
    "kv": 0.08,             # throttle command per mm of distance error
    "max_cmd": 40,          # hard clamp on every motor command in this mode
    "rotate_floor": 12,     # min rotate command that actually turns the wheels
    "throttle_floor": 15,   # min throttle command that actually drives
    "search_speed": 25,     # rotate command while hunting for a marker
    "bearing_deadband": 3.0,
    "bearing_recenter": 12.0,  # during APPROACH, drift beyond this -> back to CENTER
    "fps": 10.0,
    "confirm_frames": 3,    # consecutive detections before we act
    "hold_frames": 5,       # missed frames tolerated before declaring LOST
    "search_timeout_s": 20.0,
    "lost_search_s": 5.0,
    "tof_stop_mm": 250.0,   # ToF obstacle override: closer than this -> stop
}


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _floor_cmd(v, floor):
    """Push a small nonzero command up to the motor's stall floor, keeping sign.
    Commands under the deadband should be passed as 0 (handled by caller)."""
    if v == 0:
        return 0
    mag = max(abs(v), floor)
    return int(math.copysign(mag, v))


# --- ArUco detector (compatible across OpenCV 4.6- and 4.7+ API split) --------
def _make_detector():
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    try:
        params = cv2.aruco.DetectorParameters()          # OpenCV >= 4.7
        detector = cv2.aruco.ArucoDetector(d, params)
        return lambda gray: detector.detectMarkers(gray)
    except AttributeError:
        params = cv2.aruco.DetectorParameters_create()   # OpenCV <= 4.6
        return lambda gray: cv2.aruco.detectMarkers(gray, d, parameters=params)


def _measure(corners, focal_px, marker_size_mm, frame_w):
    """corners: (4,2) float array. Returns (distance_mm, bearing_deg, px_width)."""
    c = corners.reshape(4, 2)
    # Mean of the two horizontal edges (top: 0-1, bottom: 3-2) resists tilt skew.
    top = np.linalg.norm(c[0] - c[1])
    bottom = np.linalg.norm(c[3] - c[2])
    px_width = (top + bottom) / 2.0
    if px_width < 1e-3:
        return None
    distance_mm = marker_size_mm * focal_px / px_width
    cx = float(c[:, 0].mean())
    bearing_deg = math.degrees(math.atan2(cx - frame_w / 2.0, focal_px))
    return distance_mm, bearing_deg, px_width


class MarkerNavigator:
    """Background drive-to-marker controller. One run per start()."""

    def __init__(self, config=None):
        cfg = dict(DEFAULT_CONFIG)
        if config:
            cfg.update({k: v for k, v in config.items() if v is not None or k == "target_marker_id"})
        self.cfg = cfg
        self._thread = None
        self._stop = threading.Event()
        self.motor_api = None
        self.tof_reader = None
        self.status_cb = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, motor_api, tof_reader=None, status_cb=None, can_strafe=True):
        """Launch the control loop in a daemon thread.

        motor_api  : the active drive module (throttle_value/direction/rotate_angle/stop).
        tof_reader : optional () -> (distance_mm, valid) for the obstacle override.
        status_cb  : optional (dict) -> None, called each tick with nav status.
        can_strafe : True for mecanum (centre by strafing), False for differential.
        """
        if not CV_AVAILABLE:
            return False
        if self.running:
            return False
        self.motor_api = motor_api
        self.tof_reader = tof_reader
        self.status_cb = status_cb
        self.can_strafe = can_strafe
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="marker-nav")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self.motor_api:
            try:
                self.motor_api.stop()
            except Exception as e:
                logger.error(f"stop(): motor stop failed: {e}")

    # --- helpers ----------------------------------------------------------
    def _emit(self, **kw):
        if self.status_cb:
            try:
                self.status_cb(kw)
            except Exception:
                pass

    def _tof_blocked(self):
        if not self.tof_reader:
            return False
        try:
            dist, valid = self.tof_reader()
        except Exception:
            return False
        return valid and dist is not None and dist < self.cfg["tof_stop_mm"]

    def _pick_target(self, detections, locked_id):
        """detections: list of (id, distance, bearing, px_width). Returns one or None."""
        want = self.cfg["target_marker_id"]
        if locked_id is not None:
            for det in detections:
                if det[0] == locked_id:
                    return det
            return None  # locked marker not in view this frame
        if want is not None:
            for det in detections:
                if det[0] == want:
                    return det
            return None
        # No preference: nearest = largest pixel width.
        return max(detections, key=lambda d: d[3])

    # --- main loop --------------------------------------------------------
    def _run(self):
        cfg = self.cfg
        cap = None
        try:
            cap = cv2.VideoCapture(cfg["camera"])
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["frame_width"])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["frame_height"])
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # drop stale frames
            except Exception:
                pass
            if not cap.isOpened():
                logger.error(f"Vision: cannot open camera {cfg['camera']}")
                self._emit(state="ERROR", note="camera open failed")
                return

            detect = _make_detector()
            period = 1.0 / cfg["fps"]
            read_fails = 0
            state = "SEARCH"
            locked_id = None
            confirm = 0            # consecutive good detections
            miss = 0              # consecutive missed frames (for LOST hold)
            search_start = time.time()
            lost_start = 0.0
            last_bearing = 0.0
            centered = 0          # consecutive centered frames

            logger.info("Vision: drive-to-marker started")

            while not self._stop.is_set():
                tick = time.time()

                ok, frame = cap.read()
                if not ok or frame is None:
                    read_fails += 1
                    if read_fails >= 10:
                        logger.error("Vision: 10 consecutive frame reads failed, aborting")
                        break
                    time.sleep(period)
                    continue
                read_fails = 0

                # ToF obstacle override — highest priority, every tick.
                if self._tof_blocked():
                    self.motor_api.stop()
                    self._emit(state="ARRIVED", note="tof obstacle", marker_id=locked_id)
                    logger.info("Vision: ToF obstacle -> stop")
                    break

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                corners, ids, _ = detect(gray)
                frame_w = frame.shape[1]

                detections = []
                if ids is not None:
                    for i, mid in enumerate(ids.flatten()):
                        m = _measure(corners[i], cfg["focal_px"], cfg["marker_size_mm"], frame_w)
                        if m:
                            detections.append((int(mid), m[0], m[1], m[2]))

                target = self._pick_target(detections, locked_id) if detections else None

                # --- SEARCH -----------------------------------------------
                if state == "SEARCH":
                    if target:
                        confirm += 1
                        if confirm >= cfg["confirm_frames"]:
                            locked_id = target[0]
                            state, confirm, centered = "CENTER", 0, 0
                            logger.info(f"Vision: locked marker {locked_id} -> CENTER")
                    else:
                        confirm = 0
                        self.motor_api.rotate_angle(int(cfg["search_speed"]))
                        if time.time() - search_start > cfg["search_timeout_s"]:
                            self.motor_api.stop()
                            self._emit(state="GIVEUP", note="search timeout")
                            logger.info("Vision: search timeout -> give up")
                            break
                    self._emit(state=state, note="searching" if not target else "confirming")

                # --- CENTER / APPROACH share the reacquire path -----------
                elif state in ("CENTER", "APPROACH"):
                    if not target:
                        miss += 1
                        if miss > cfg["hold_frames"]:
                            state, lost_start = "LOST", time.time()
                            self.motor_api.stop()
                            logger.info("Vision: marker lost -> LOST")
                        self._emit(state=state, note="holding", marker_id=locked_id)
                    else:
                        miss = 0
                        _, dist, bearing, _ = target
                        last_bearing = bearing
                        dband = cfg["bearing_deadband"]

                        if state == "CENTER":
                            if abs(bearing) < dband:
                                centered += 1
                                self.motor_api.stop()
                                if centered >= cfg["confirm_frames"]:
                                    state, centered = "APPROACH", 0
                                    logger.info("Vision: centered -> APPROACH")
                            else:
                                centered = 0
                                if self.can_strafe and abs(bearing) < 8.0:
                                    cmd = _floor_cmd(_clamp(cfg["kw"] * bearing, -cfg["max_cmd"], cfg["max_cmd"]),
                                                     cfg["rotate_floor"])
                                    self.motor_api.direction(int(_clamp(cmd, -cfg["max_cmd"], cfg["max_cmd"])), 0)
                                else:
                                    cmd = _floor_cmd(_clamp(cfg["kw"] * bearing, -cfg["max_cmd"], cfg["max_cmd"]),
                                                     cfg["rotate_floor"])
                                    self.motor_api.rotate_angle(int(_clamp(cmd, -cfg["max_cmd"], cfg["max_cmd"])))

                        else:  # APPROACH
                            if dist <= cfg["standoff_mm"]:
                                self.motor_api.stop()
                                state = "ARRIVED"
                                self._emit(state="ARRIVED", distance_mm=round(dist, 1),
                                           bearing_deg=round(bearing, 1), marker_id=locked_id)
                                logger.info(f"Vision: ARRIVED at {dist:.0f}mm")
                                break
                            if abs(bearing) > cfg["bearing_recenter"]:
                                self.motor_api.stop()
                                state = "CENTER"
                            else:
                                thr = _floor_cmd(_clamp(cfg["kv"] * (dist - cfg["standoff_mm"]),
                                                        0, cfg["max_cmd"]), cfg["throttle_floor"])
                                self.motor_api.throttle_value(int(thr))
                                # small steering trim while approaching
                                if abs(bearing) > dband:
                                    trim = _floor_cmd(_clamp(cfg["kw"] * bearing, -cfg["max_cmd"], cfg["max_cmd"]),
                                                      cfg["rotate_floor"])
                                    self.motor_api.rotate_angle(int(_clamp(trim, -cfg["max_cmd"], cfg["max_cmd"])))
                                else:
                                    self.motor_api.rotate_angle(0)

                        if state in ("CENTER", "APPROACH"):
                            self._emit(state=state, distance_mm=round(dist, 1),
                                       bearing_deg=round(bearing, 1), marker_id=locked_id)

                # --- LOST -------------------------------------------------
                elif state == "LOST":
                    if target:
                        state, miss = "CENTER", 0
                        logger.info("Vision: reacquired -> CENTER")
                        self._emit(state=state, marker_id=locked_id)
                    elif time.time() - lost_start > cfg["lost_search_s"]:
                        self.motor_api.stop()
                        self._emit(state="GIVEUP", note="lost timeout")
                        logger.info("Vision: lost timeout -> give up")
                        break
                    else:
                        # slow-search toward the side we last saw the marker
                        d = cfg["search_speed"] if last_bearing >= 0 else -cfg["search_speed"]
                        self.motor_api.rotate_angle(int(d))
                        self._emit(state="LOST", note="searching")

                # pace the loop
                dt = time.time() - tick
                if dt < period:
                    time.sleep(period - dt)

        except Exception as e:
            logger.error(f"Vision loop error: {e}")
        finally:
            if self.motor_api:
                try:
                    self.motor_api.stop()
                except Exception:
                    pass
            if cap is not None:
                cap.release()
            logger.info("Vision: drive-to-marker stopped")


def calibrate(camera=0, marker_size_mm=100.0, known_distance_mm=500.0,
              frame_w=1280, frame_h=720):
    """One-time focal-length capture. Place a marker flat, facing the camera, at
    exactly known_distance_mm, then run this. Returns focal_px to put in config.

    focal_px = marker_pixel_width * known_distance_mm / marker_size_mm
    """
    if not CV_AVAILABLE:
        print("cv2 not available")
        return None
    cap = cv2.VideoCapture(camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_h)
    detect = _make_detector()
    focal = None
    try:
        for _ in range(60):  # ~a few seconds of frames to grab a clean read
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detect(gray)
            if ids is not None and len(corners):
                c = corners[0].reshape(4, 2)
                px = (np.linalg.norm(c[0] - c[1]) + np.linalg.norm(c[3] - c[2])) / 2.0
                focal = px * known_distance_mm / marker_size_mm
                print(f"marker_px={px:.1f}  ->  focal_px={focal:.1f}")
                break
    finally:
        cap.release()
    if focal is None:
        print("No marker detected — check lighting / marker / camera index.")
    return focal


if __name__ == "__main__":
    # Smoke test / calibration helper (run on the board with a webcam + marker).
    #   python3 marker_vision.py            -> live distance/bearing readout
    #   python3 marker_vision.py calibrate  -> capture focal_px at 500mm
    import sys

    logging.basicConfig(level=logging.INFO)

    # self-check the pure math with no hardware needed
    class _FakeCorners:
        pass
    fake = np.array([[[100, 100], [200, 100], [200, 200], [100, 200]]], dtype=np.float32)
    d, b, w = _measure(fake, focal_px=900.0, marker_size_mm=100.0, frame_w=1280)
    assert abs(w - 100.0) < 1e-6, w
    assert abs(d - 900.0) < 1e-6, d           # 100mm * 900px / 100px = 900mm
    assert b < 0, b                            # marker centre (150) left of 640 -> negative bearing
    print(f"self-check OK: dist={d:.0f}mm bearing={b:.1f}deg width={w:.0f}px")

    if len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        calibrate()
    elif CV_AVAILABLE:
        cap = cv2.VideoCapture(0)
        detect = _make_detector()
        print("Live readout — Ctrl-C to quit.")
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                corners, ids, _ = detect(gray)
                if ids is not None:
                    for i, mid in enumerate(ids.flatten()):
                        m = _measure(corners[i], 900.0, 100.0, frame.shape[1])
                        if m:
                            print(f"id={mid}  dist={m[0]:.0f}mm  bearing={m[1]:+.1f}deg")
                time.sleep(0.1)
        except KeyboardInterrupt:
            cap.release()
