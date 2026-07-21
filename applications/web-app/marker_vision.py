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
    "gst_pipeline": None,   # if set, open THIS GStreamer pipeline via CAP_GSTREAMER
                            # instead of "camera". Needed for the STM32MP DCMIPP +
                            # IMX335 main pipe (NV12), which raw V4L2 can't grab.
                            # Must end in: ... ! videoconvert ! appsink  (BGR frames).
                            # {w}/{h} placeholders are filled from frame_width/height.
    "frame_width": 1280,
    "frame_height": 720,
    "marker_size_mm": 100.0,
    "focal_px": 300.0,      # MUST calibrate per camera/res; default ~ 1280px @ 60-70deg HFOV
    "standoff_mm": 400.0,   # stop this far from the marker
    "target_marker_id": None,  # None = lock onto the nearest (largest) marker
    "kw": 2.5,              # rotate command per degree of bearing error
    "kv": 0.08,             # throttle command per mm of distance error
    "max_cmd": 40,          # hard clamp on every motor command in this mode
    "rotate_floor": 25,     # min rotate command that actually turns the wheels
    "throttle_floor": 25,   # min throttle command that actually drives
    # NOTE: motors physically stall below ~25% duty, so both floors are 25 --
    # any computed command below that is bumped up to 25 (when outside the
    # deadband) or sent as 0 (inside it). Never emit 1..24: it just whines.
    "search_speed": 25,     # rotate command while hunting for a marker
    "bearing_deadband": 3.0,
    "bearing_recenter": 12.0,  # during APPROACH, drift beyond this -> back to CENTER
    "fps": 10.0,
    "confirm_frames": 3,    # consecutive detections before we act
    "hold_frames": 5,       # missed frames tolerated before declaring LOST
    "search_timeout_s": 20.0,
    "lost_search_s": 5.0,
    "tof_stop_mm": 250.0,   # ToF obstacle override: closer than this -> stop
    "stream": True,         # publish annotated JPEG frames for the MJPEG feed
    "stream_quality": 60,   # JPEG quality 1-100 (lower = less CPU/bandwidth)
    "stream_fps": 15.0,     # camera grab + feed rate (always-on controller feed)
    # --- local display (HDMI/DSI panel wired to the board) ---
    "local_display": False,     # also render the annotated frame in a cv2 window
    "local_display_window": "RBT01 Marker Vision",  # window title
    "local_display_fullscreen": False,  # borderless fullscreen on the panel
    # On Wayland/Weston (ST demo image) OpenCV's imshow can't draw (GTK is X11-
    # only). Set wayland_display=True to push annotated frames to a waylandsink
    # via GStreamer instead. Requires env XDG_RUNTIME_DIR=/run/user/<uid> and
    # WAYLAND_DISPLAY=<socket> pointing at the running weston.
    "wayland_display": False,
    # --- follow-me mode (continuous tracking, keeps a set distance) ---
    "follow_marker_id": None,   # which marker to follow; None = nearest in view
    "follow_distance_mm": 600.0,  # gap to maintain from the marker
    "follow_deadband_mm": 80.0,   # distance error inside this -> no forward/back
    "follow_bearing_deadband": 8.0,  # |bearing| under this -> "centered", don't rotate
    "follow_rotate_pulse_s": 0.12,   # rotate this long then STOP, so it can't
                                     # overshoot while blind between camera frames
    "follow_settle_s": 0.10,         # pause after a rotate pulse before re-reading
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


def _open_capture(cfg):
    """Open the camera per config and return an opened cv2.VideoCapture (or a
    closed one — caller checks isOpened()).

    Two backends:
      * cfg["gst_pipeline"] set  -> CAP_GSTREAMER with that pipeline string.
        {w}/{h} in the string are substituted from frame_width/height. Escape
        hatch only; not needed for the DCMIPP main pipe (see below).
      * otherwise -> V4L2 on cfg["camera"] (int index or "/dev/videoN").

    CRITICAL (STM32MP DCMIPP + IMX335): do NOT set CAP_PROP_FRAME_WIDTH/HEIGHT on
    a /dev/videoN path. The DCMIPP media-controller pipeline is fixed by media-ctl
    (640x480 RGB here) and cannot be reconfigured via VIDIOC_S_FMT from OpenCV's
    V4L2 backend — attempting it silently stops the stream. We take the pipeline's
    native resolution as-is. Only integer/USB sources get width/height set.
    """
    gst = cfg.get("gst_pipeline")
    if gst:
        pipeline = gst.format(w=cfg["frame_width"], h=cfg["frame_height"])
        logger.info(f"Opening camera via GStreamer: {pipeline}")
        return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

    src = cfg["camera"]
    is_devpath = isinstance(src, str) and src.startswith("/dev/")
    cap = cv2.VideoCapture(src, cv2.CAP_V4L2) if is_devpath else cv2.VideoCapture(src)
    if not is_devpath:
        # USB/index source: native res is negotiable, so honor the config.
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["frame_width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["frame_height"])
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


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


class CameraStream:
    """Single owner of the webcam. Runs one background grab loop that always
    reads frames, detects ArUco markers, publishes an annotated JPEG for the
    always-on controller feed, and exposes the latest detections so the
    navigator can consume them WITHOUT opening the camera a second time
    (V4L2 forbids two opens on one device).

    Lifecycle is independent of autopilot: started at server startup, stays
    running so the feed is live whether or not vision nav is active.
    """

    def __init__(self, config=None):
        cfg = dict(DEFAULT_CONFIG)
        if config:
            cfg.update({k: v for k, v in config.items() if v is not None or k == "target_marker_id"})
        self.cfg = cfg
        self.quality = int(cfg.get("stream_quality", 60))
        self.stream_fps = float(cfg.get("stream_fps", 15.0))
        self.local_display = bool(cfg.get("local_display", False))
        self._window_ready = False  # created lazily on the grab thread
        self.wayland_display = bool(cfg.get("wayland_display", False))
        self._wl_writer = None      # cv2.VideoWriter -> waylandsink, lazy
        self._thread = None
        self._stop = threading.Event()
        self._jpeg = None
        self._jpeg_lock = threading.Lock()
        # (detections, frame_w, seq) — seq lets the navigator skip stale frames.
        self._latest = None
        self._seq = 0
        self._latest_lock = threading.Lock()
        self._banner = "LIVE"
        self._banner_lock = threading.Lock()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if not CV_AVAILABLE or self.running:
            return self.running
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="camera-stream")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()

    def get_frame(self):
        """Latest annotated JPEG bytes, or None if nothing published yet."""
        with self._jpeg_lock:
            return self._jpeg

    def latest_detections(self):
        """(detections, frame_w, seq). detections: list of (id, dist, bearing,
        px_width). seq increments per grabbed frame so callers can detect new
        frames. Returns (None, 0, seq) when no frame yet."""
        with self._latest_lock:
            if self._latest is None:
                return (None, 0, self._seq)
            return (self._latest[0], self._latest[1], self._latest[2])

    def set_banner(self, text):
        """Override the on-frame status text (navigator uses this to show its
        state). Pass None/"" to fall back to the default LIVE banner."""
        with self._banner_lock:
            self._banner = text or "LIVE"

    def _run(self):
        cfg = self.cfg
        cap = None
        try:
            cap = _open_capture(cfg)
            if not cap.isOpened():
                logger.error(f"CameraStream: cannot open camera "
                             f"{cfg.get('gst_pipeline') or cfg['camera']}")
                return

            detect = _make_detector()
            period = 1.0 / self.stream_fps if self.stream_fps > 0 else 0.066
            read_fails = 0
            logger.info(f"CameraStream: live on camera {cfg['camera']}")

            while not self._stop.is_set():
                tick = time.time()
                ok, frame = cap.read()
                if not ok or frame is None:
                    read_fails += 1
                    if read_fails >= 20:
                        logger.error("CameraStream: 20 consecutive read failures, aborting")
                        break
                    time.sleep(period)
                    continue
                read_fails = 0

                frame_w = frame.shape[1]
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                corners, ids, _ = detect(gray)

                detections = []
                if ids is not None:
                    for i, mid in enumerate(ids.flatten()):
                        m = _measure(corners[i], cfg["focal_px"], cfg["marker_size_mm"], frame_w)
                        if m:
                            detections.append((int(mid), m[0], m[1], m[2]))

                with self._latest_lock:
                    self._seq += 1
                    self._latest = (detections, frame_w, self._seq)

                self._publish(frame, ids, corners, detections)

                dt = time.time() - tick
                if dt < period:
                    time.sleep(period - dt)
        except Exception as e:
            logger.error(f"CameraStream loop error: {e}")
        finally:
            with self._jpeg_lock:
                self._jpeg = None
            if self._window_ready:
                try:
                    cv2.destroyWindow(self._window_name)
                    cv2.waitKey(1)
                except Exception:
                    pass
                self._window_ready = False
            if self._wl_writer is not None:
                try:
                    self._wl_writer.release()
                except Exception:
                    pass
                self._wl_writer = None
            if cap is not None:
                cap.release()
            logger.info("CameraStream: stopped")

    def _publish(self, frame, ids, corners, detections):
        try:
            if ids is not None and len(corners):
                cv2.aruco.drawDetectedMarkers(frame, corners, ids)
            with self._banner_lock:
                banner = self._banner
            # In the default (non-nav) banner, append the nearest marker's read.
            if banner == "LIVE" and detections:
                nearest = max(detections, key=lambda d: d[3])
                banner = f"LIVE  #{nearest[0]}  {nearest[1]:.0f}mm  {nearest[2]:+.1f}deg"
            cv2.putText(frame, banner, (8, 24), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 255, 0), 2, cv2.LINE_AA)
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
            if ok:
                with self._jpeg_lock:
                    self._jpeg = buf.tobytes()
            if self.local_display:
                self._show_local(frame)
            if self.wayland_display:
                self._show_wayland(frame)
        except Exception as e:
            logger.debug(f"CameraStream publish failed: {e}")

    def _show_wayland(self, frame):
        """Push the annotated frame to a Wayland surface via GStreamer
        (appsrc -> videoconvert -> waylandsink). This is the display path for the
        ST Weston image, where OpenCV's imshow (GTK/X11) can't draw. Lazily builds
        a cv2.VideoWriter once the frame size is known; disables itself on failure
        so the MJPEG feed keeps running. Needs XDG_RUNTIME_DIR + WAYLAND_DISPLAY
        env pointing at the running weston compositor."""
        try:
            if self._wl_writer is None:
                h, w = frame.shape[:2]
                fps = self.stream_fps if self.stream_fps > 0 else 15.0
                pipeline = ("appsrc ! videoconvert ! "
                            "waylandsink sync=false")
                writer = cv2.VideoWriter(pipeline, cv2.CAP_GSTREAMER, 0,
                                         fps, (w, h), True)
                if not writer.isOpened():
                    raise RuntimeError("waylandsink VideoWriter did not open "
                                       "(check XDG_RUNTIME_DIR/WAYLAND_DISPLAY)")
                self._wl_writer = writer
                logger.info(f"Wayland display: streaming {w}x{h}@{fps:.0f} to waylandsink")
            self._wl_writer.write(frame)
        except Exception as e:
            logger.warning(f"Wayland display unavailable, disabling it: {e}")
            self.wayland_display = False
            if self._wl_writer is not None:
                try:
                    self._wl_writer.release()
                except Exception:
                    pass
                self._wl_writer = None

    def _show_local(self, frame):
        """Render the annotated frame in a cv2 window on the board's attached
        display. Same frame as the MJPEG feed (single camera open). Best-effort:
        if there's no GUI backend (no Wayland/X, or opencv built headless) it
        disables itself after the first failure so the feed keeps running."""
        try:
            if not self._window_ready:
                win = self.cfg.get("local_display_window", "RBT01 Marker Vision")
                if self.cfg.get("local_display_fullscreen", False):
                    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
                    cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_FULLSCREEN)
                else:
                    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
                self._window_name = win
                self._window_ready = True
            cv2.imshow(self._window_name, frame)
            cv2.waitKey(1)  # required to pump the GUI event loop / actually draw
        except Exception as e:
            logger.warning(f"Local display unavailable, disabling it: {e}")
            self.local_display = False


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
        self.camera = None  # shared CameraStream; navigator reads its detections

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, motor_api, camera, tof_reader=None, status_cb=None, can_strafe=True):
        """Launch the control loop in a daemon thread.

        motor_api  : the active drive module (throttle_value/direction/rotate_angle/stop).
        camera     : the shared CameraStream to read detections from (it owns the
                     webcam; the navigator never opens the device itself).
        tof_reader : optional () -> (distance_mm, valid) for the obstacle override.
        status_cb  : optional (dict) -> None, called each tick with nav status.
        can_strafe : True for mecanum (centre by strafing), False for differential.
        """
        if not CV_AVAILABLE:
            return False
        if self.running:
            return False
        if camera is None or not camera.running:
            logger.error("Vision: camera stream not running; cannot start nav")
            return False
        self.motor_api = motor_api
        self.camera = camera
        self.tof_reader = tof_reader
        self.status_cb = status_cb
        self.can_strafe = can_strafe
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="marker-nav")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self.camera:
            self.camera.set_banner(None)  # restore default LIVE banner
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
        try:
            period = 1.0 / cfg["fps"]
            state = "SEARCH"
            locked_id = None
            confirm = 0            # consecutive good detections
            miss = 0              # consecutive missed frames (for LOST hold)
            search_start = time.time()
            lost_start = 0.0
            last_bearing = 0.0
            centered = 0          # consecutive centered frames
            last_seq = -1

            logger.info("Vision: drive-to-marker started")

            while not self._stop.is_set():
                tick = time.time()

                # Consume the latest detections from the shared camera stream
                # (it owns the device and draws the feed). Wait for a *new*
                # frame so we act on fresh data, not the same frame twice.
                detections, frame_w, seq = self.camera.latest_detections()
                if seq == last_seq or detections is None:
                    time.sleep(period / 2)
                    continue
                last_seq = seq

                # ToF obstacle override — highest priority, every tick.
                if self._tof_blocked():
                    self.motor_api.stop()
                    self._emit(state="ARRIVED", note="tof obstacle", marker_id=locked_id)
                    logger.info("Vision: ToF obstacle -> stop")
                    break

                target = self._pick_target(detections, locked_id) if detections else None

                # Show the controller feed what the nav is doing this tick.
                _banner = state
                if locked_id is not None:
                    _banner += f" #{locked_id}"
                if target:
                    _banner += f" {target[1]:.0f}mm {target[2]:+.1f}deg"
                self.camera.set_banner(_banner)

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
            if self.camera:
                self.camera.set_banner(None)  # restore default LIVE banner
            logger.info("Vision: drive-to-marker stopped")


class MarkerFollower:
    """Follow-me controller: continuously tracks ONE marker and keeps a set
    distance from it. Unlike MarkerNavigator (drive-to-marker) this never
    terminally "arrives" -- it runs until stopped, reversing when the marker
    gets too close and advancing when it moves away. Consumes detections from
    the shared CameraStream (never opens the camera itself).

    Config keys used: follow_marker_id, follow_distance_mm, follow_deadband_mm,
    plus the shared kw/kv/max_cmd/*_floor/bearing_deadband/fps/hold_frames/
    focal_px/marker_size_mm and tof_stop_mm.
    """

    def __init__(self, config=None):
        cfg = dict(DEFAULT_CONFIG)
        if config:
            cfg.update({k: v for k, v in config.items()
                        if v is not None or k in ("follow_marker_id",)})
        self.cfg = cfg
        self._thread = None
        self._stop = threading.Event()
        self.motor_api = None
        self.camera = None
        self.tof_reader = None
        self.status_cb = None
        self.can_strafe = True

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, motor_api, camera, tof_reader=None, status_cb=None, can_strafe=True):
        """Launch the follow loop in a daemon thread. Args mirror
        MarkerNavigator.start(); camera is the shared CameraStream."""
        if not CV_AVAILABLE:
            return False
        if self.running:
            return False
        if camera is None or not camera.running:
            logger.error("Follow: camera stream not running; cannot start")
            return False
        self.motor_api = motor_api
        self.camera = camera
        self.tof_reader = tof_reader
        self.status_cb = status_cb
        self.can_strafe = can_strafe
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="marker-follow")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self.camera:
            self.camera.set_banner(None)
        if self.motor_api:
            try:
                self.motor_api.stop()
            except Exception as e:
                logger.error(f"follow stop(): motor stop failed: {e}")

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

    def _pick(self, detections):
        """Follow the configured marker id, or the nearest one if unset."""
        want = self.cfg["follow_marker_id"]
        if want is not None:
            for det in detections:
                if det[0] == want:
                    return det
            return None
        return max(detections, key=lambda d: d[3]) if detections else None

    def _run(self):
        cfg = self.cfg
        try:
            period = 1.0 / cfg["fps"]
            follow_mm = float(cfg["follow_distance_mm"])
            dband_mm = float(cfg["follow_deadband_mm"])
            maxc = cfg["max_cmd"]
            miss = 0
            last_seq = -1
            logger.info(f"Follow: started (id={cfg['follow_marker_id']}, "
                        f"dist={follow_mm:.0f}mm)")

            while not self._stop.is_set():
                tick = time.time()

                detections, frame_w, seq = self.camera.latest_detections()
                if seq == last_seq or detections is None:
                    time.sleep(period / 2)
                    continue
                last_seq = seq

                # ToF obstacle override -- highest priority. Something right in
                # front (not necessarily the marker) -> stop, don't reverse-hunt.
                if self._tof_blocked():
                    self.motor_api.stop()
                    self.camera.set_banner("FOLLOW blocked (ToF)")
                    self._emit(state="BLOCKED", note="tof obstacle")
                    time.sleep(period)
                    continue

                target = self._pick(detections) if detections else None

                if target is None:
                    # Marker lost -> stop and wait (per design). Hold a few
                    # frames of tolerance to ride out detection flicker.
                    miss += 1
                    if miss >= cfg["hold_frames"]:
                        self.motor_api.stop()
                        self.camera.set_banner("FOLLOW waiting (no marker)")
                        self._emit(state="WAITING", note="marker lost")
                    time.sleep(period)
                    continue
                miss = 0

                _, dist, bearing, _ = target

                # --- rotation: PULSE toward center, don't spin continuously ---
                # At camera fps the robot turns "blind" between frames; a steady
                # rotate command overshoots and the marker leaves the FOV (lost).
                # Instead: if clearly off-center, rotate for a short pulse then
                # STOP and wait for a fresh frame before deciding again. While
                # correcting bearing we do NOT drive forward/back -- center first.
                if abs(bearing) > cfg["follow_bearing_deadband"]:
                    cmd = _floor_cmd(_clamp(cfg["kw"] * bearing, -maxc, maxc),
                                     cfg["rotate_floor"])
                    cmd = int(_clamp(cmd, -maxc, maxc))
                    # Rotate to FACE the marker (turn the robot), not strafe. A
                    # follow-me should point at what it follows; +bearing (marker
                    # to the right) -> +rotate (turn right) toward it.
                    self.motor_api.rotate_angle(cmd)
                    time.sleep(cfg["follow_rotate_pulse_s"])
                    self.motor_api.stop()
                    self.camera.set_banner(
                        f"FOLLOW #{target[0]} {dist:.0f}mm {bearing:+.1f}deg CENTERING")
                    self._emit(state="CENTERING", distance_mm=round(dist, 1),
                               bearing_deg=round(bearing, 1), marker_id=target[0],
                               target_mm=follow_mm)
                    time.sleep(cfg["follow_settle_s"])  # let motion stop before re-read
                    last_seq = -1  # force a fresh frame next iteration
                    continue

                # Centered enough -> hold heading and manage distance only.
                self.motor_api.rotate_angle(0)

                # --- forward/back: keep the set distance (reverse if too close) ---
                err = dist - follow_mm  # +ve: too far (advance); -ve: too close (reverse)
                if abs(err) <= dband_mm:
                    self.motor_api.throttle_value(0)
                    state = "HOLDING"
                else:
                    thr = _floor_cmd(_clamp(cfg["kv"] * err, -maxc, maxc),
                                     cfg["throttle_floor"])
                    self.motor_api.throttle_value(int(_clamp(thr, -maxc, maxc)))
                    state = "ADVANCING" if err > 0 else "REVERSING"

                banner = f"FOLLOW #{target[0]} {dist:.0f}mm {bearing:+.1f}deg {state}"
                self.camera.set_banner(banner)
                self._emit(state=state, distance_mm=round(dist, 1),
                           bearing_deg=round(bearing, 1), marker_id=target[0],
                           target_mm=follow_mm)

                dt = time.time() - tick
                if dt < period:
                    time.sleep(period - dt)

        except Exception as e:
            logger.error(f"Follow loop error: {e}")
        finally:
            if self.motor_api:
                try:
                    self.motor_api.stop()
                except Exception:
                    pass
            if self.camera:
                self.camera.set_banner(None)
            logger.info("Follow: stopped")


def calibrate(camera=0, marker_size_mm=100.0, known_distance_mm=500.0,
              frame_w=1280, frame_h=720, gst_pipeline=None):
    """One-time focal-length capture. Place a marker flat, facing the camera, at
    exactly known_distance_mm, then run this. Returns focal_px to put in config.

    focal_px = marker_pixel_width * known_distance_mm / marker_size_mm
    """
    if not CV_AVAILABLE:
        print("cv2 not available")
        return None
    cap = _open_capture({"camera": camera, "gst_pipeline": gst_pipeline,
                         "frame_width": frame_w, "frame_height": frame_h})
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
    # Camera / marker_size / focal are read from robot_config.json["vision"] so
    # this matches what the running app uses (camera index is board-specific).
    import json
    import os
    import sys

    logging.basicConfig(level=logging.INFO)

    # self-check the pure math with no hardware needed
    fake = np.array([[[100, 100], [200, 100], [200, 200], [100, 200]]], dtype=np.float32)
    d, b, w = _measure(fake, focal_px=900.0, marker_size_mm=100.0, frame_w=1280)
    assert abs(w - 100.0) < 1e-6, w
    assert abs(d - 900.0) < 1e-6, d           # 100mm * 900px / 100px = 900mm
    assert b < 0, b                            # marker centre (150) left of 640 -> negative bearing
    print(f"self-check OK: dist={d:.0f}mm bearing={b:.1f}deg width={w:.0f}px")

    cfg = dict(DEFAULT_CONFIG)
    _cfg_path = os.path.join(os.path.dirname(__file__), "robot_config.json")
    try:
        cfg.update(json.load(open(_cfg_path)).get("vision", {}))
    except Exception:
        pass
    cam, size, focal = cfg["camera"], cfg["marker_size_mm"], cfg["focal_px"]

    if len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        calibrate(camera=cam, marker_size_mm=size,
                  frame_w=cfg["frame_width"], frame_h=cfg["frame_height"],
                  gst_pipeline=cfg.get("gst_pipeline"))
    elif CV_AVAILABLE:
        cap = _open_capture(cfg)
        detect = _make_detector()
        # Preview: on Wayland (ST Weston image) imshow's GTK backend can't draw,
        # so if wayland_display is set push frames to waylandsink via a
        # VideoWriter; otherwise use imshow. Either auto-disables on failure.
        use_wl = bool(cfg.get("wayland_display", False))
        show = True
        wl_writer = None
        print(f"Live readout (camera={cam}, focal_px={focal}) — 'q' or Ctrl-C to quit.")
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                corners, ids, _ = detect(gray)
                if ids is not None:
                    cv2.aruco.drawDetectedMarkers(frame, corners, ids)
                    for i, mid in enumerate(ids.flatten()):
                        m = _measure(corners[i], focal, size, frame.shape[1])
                        if m:
                            print(f"id={mid}  dist={m[0]:.0f}mm  bearing={m[1]:+.1f}deg")
                            c = corners[i].reshape(4, 2)
                            cv2.putText(frame, f"#{mid} {m[0]:.0f}mm {m[1]:+.1f}deg",
                                        (int(c[:, 0].min()), int(c[:, 1].min()) - 8),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
                                        cv2.LINE_AA)
                if show and use_wl:
                    try:
                        if wl_writer is None:
                            h, w = frame.shape[:2]
                            wl_writer = cv2.VideoWriter(
                                "appsrc ! videoconvert ! waylandsink sync=false",
                                cv2.CAP_GSTREAMER, 0, 15.0, (w, h), True)
                            if not wl_writer.isOpened():
                                raise RuntimeError("waylandsink writer did not open "
                                                   "(check XDG_RUNTIME_DIR/WAYLAND_DISPLAY)")
                        wl_writer.write(frame)
                    except Exception as e:
                        print(f"(preview off — waylandsink failed: {e})")
                        show = False
                elif show:
                    try:
                        cv2.imshow("marker_vision", frame)
                        if (cv2.waitKey(1) & 0xFF) == ord("q"):
                            break
                    except Exception as e:
                        print(f"(preview off — no display: {e})")
                        show = False
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            cap.release()
            if wl_writer is not None:
                try:
                    wl_writer.release()
                except Exception:
                    pass
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
