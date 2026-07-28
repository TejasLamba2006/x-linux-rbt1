# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

X-LINUX-RBT1 is an STMicroelectronics Linux software package for the X-STM32MP-RBT01 robotics
expansion board (STSPIN948 motor drivers, VL53L5CX ToF sensor, ISM330DHCX IMU, LPS22HH pressure,
IIS2MDC magnetometer). The actual application code lives entirely under `applications/web-app/` —
a FastAPI + WebSocket backend that serves a joystick-based remote control web app, running directly
on the STM32MP board (not on this dev machine).

There is no local build/test/lint toolchain — code only truly runs on the target board (Python 3
under Yocto/OpenSTLinux). Treat most verification as manual/board-based rather than automated.
The one exception is `intent_classifier/test_intent.py` (58 pytest tests for the voice model),
which can run on any machine with `onnxruntime` + `numpy` + `tokenizers`.

## Workflow

1. Edit files locally in this repo.
2. Commit and push to GitHub.
3. On the board: `cd /usr/local/x-linux-rbt1 && git pull`, or for quick iteration:
   `rsync -avz applications/web-app/ root@<board-ip>:/usr/local/x-linux-rbt1/`
4. Run on the board: `python3 main.py --auto` (uses saved `robot_config.json`; omit `--auto` for the interactive CLI menu).

### Useful commands (all on the board)

```bash
# Kill stuck instance
kill $(ps aux | grep 'main.py' | grep -v grep | awk '{print $2}')

# Unexport stuck PWM channels after crash
echo 1 > /sys/class/pwm/pwmchip0/unexport
echo 3 > /sys/class/pwm/pwmchip0/unexport
echo 1 > /sys/class/pwm/pwmchip8/unexport
echo 0 > /sys/class/pwm/pwmchip12/unexport

# Start headless
nohup python3 main.py --auto > /tmp/robot.log 2>&1 &

# View logs
tail -f /tmp/robot.log
```

`main.py` flags: `--auto`, `--install-service` / `--uninstall-service` / `--generate-service`
(systemd unit management).

### Known board-side gotchas (full list in AGENTS.md)

- PWM channels can get stuck after a crash → unexport via sysfs before restart.
- `netifaces` must come from `apt-get`, not pip, on Yocto.
- Pin `pydantic<2.12` (zoneinfo issue on Yocto's Python 3.12).
- `python3-opencv` must come from `apt-get` (no pip wheel for armv7/aarch64 Yocto).
- Voice control needs `onnxruntime` + `openssl` (for the self-signed TLS cert) or it silently
  disables itself; the odometry map server needs `flask`.

## Architecture

### Board/drive-type dispatch (the key indirection to understand)

The same web-app code runs on two different SoCs (STM32MP157 and STM32MP257) and two different
drive mechanics (mecanum vs. differential/normal-wheel). Both axes are auto-detected/selected at
runtime, not at build time:

- **Board detection**: `mechanumapi.py` and `normalwheelapi.py` each read
  `/proc/device-tree/compatible` to get the board name (`stm32mp257` vs `stm32mp157`) and import
  the matching low-level pin-mapping module — `stm32mp2.py` or `stm32mp1.py` — as `STSPIN`. These
  two modules define GPIO chip/pin assignments (differ per board) and expose `motor_1a/1b/2a/2b()`,
  `stop()`, `release()`. Both build on `motor/evspin948_driver.py` (an `EVSPIN948Driver`, subclass
  of `motor/stspin_driver.py`'s `STSpinDriver`) which talks to gpiod lines and `motor/configurePWM.py`'s
  `PWMController` for actual GPIO/PWM I/O.
- **Drive-type selection**: `main.py` picks between `mechanumapi.py` (omnidirectional/mecanum) and
  `normalwheelapi.py` (standard differential 4-wheel) at startup based on `robot_config.json`
  (`drive_type` key), and dynamically `import`s the chosen module as the global `motor_api`. Both
  expose a common interface: `parser(json_dict)`, `release()`, `stop()`, `throttle_value()`,
  `direction()`, `rotate_angle()`, `mode_select()`.
- When adding motor logic, mirror this dispatch pattern rather than special-casing board/drive-type
  checks inline elsewhere — `main.py` and the frontend are meant to stay agnostic to which is active.

### Runtime data flow

1. Browser opens `/static/index.html`, connects to `/ws` (WebSocket).
2. `static/js/script.js` samples joystick/dial state every 200ms and sends JSON like
   `{"throttle": ...}`, `{"dir_x": ..., "dir_y": ...}`, `{"dir_rot": ...}`, `{"mode": ...}`.
3. `main.py`'s `ConnectionManager.receive_and_process` parses each JSON line and forwards it to
   `motor_api.parser(parsed_data)` — after applying the global `max_speed_percent` scaling
   (`apply_speed_limit()`).
4. The active drive module (`mechanumapi.py` / `normalwheelapi.py`) interprets `mode` (locked /
   controller / follow-me / autopilot — only `controller` mode currently acts on throttle/dir
   commands) and computes per-wheel PWM duty/direction, calling into the board-specific `STSPIN`
   module.
5. A background thread (`tof_obstacle_detection`) polls the VL53L5CX ToF sensor
   (`vl53l5cx/vl53l5cx.py`) and force-zeroes throttle if an obstacle is closer than 20mm.

### Optional features (graceful degradation pattern)

Each optional hardware/software feature follows the same pattern: try-import at startup, set a
boolean flag, and silently disable that feature if the dependency is missing — the rest of the app
always runs. When adding new optional features, follow this exact convention.

| Feature | Guard flag | Dependencies | Import site |
|---------|-----------|-------------|-------------|
| Voice control | `INTENT_AVAILABLE` | `onnxruntime`, `tokenizers`, `numpy` | `main.py:94-99` |
| Marker vision | `CV_AVAILABLE` | `python3-opencv` (apt) | `main.py:101-111` |
| ToF obstacle detection | `tof_driver is not None` | VL53L5CX sensor on I2C | `main.py:939-961` |
| Odometry map | `odometry_process is not None` | `flask`, mouse sensor | `main.py:458-481` |

### Voice control

`main.py` adds `intent_classifier/` to `sys.path` and tries to import it at startup; if the ONNX
model or `onnxruntime` is unavailable, `INTENT_AVAILABLE` is `False` and voice control is silently
disabled. The browser transcribes speech client-side (Web Speech API) and sends `{"voice_text": ...}`
over the WebSocket; `handle_voice_command()` classifies it with the two-stage ONNX classifier
(`embedder_onnx/model_int8.onnx` + `intent_head.onnx`) and pulse-drives the active drive module's
throttle/dir/rotate functions directly (bypassing the controller/hybrid mode gate — works in any
mode except `locked`). A confidence gate (`< 0.6 → NOP`) prevents misclassifications from reaching
the motors.

The classifier uses `paraphrase-multilingual-MiniLM-L12-v2` (INT8 quantized, 112.7 MB) for
384-dim multilingual embeddings, with manual mean-pooling + L2-normalization in `infer.py`.
Tokenizer is bundled locally via `tokenizers` lib (no `transformers` runtime dependency).
9 intent labels: FORWARD, BACKWARD, STRAFE_LEFT, STRAFE_RIGHT, ROTATE_LEFT, ROTATE_RIGHT,
STOP, PULSE, NOP. PULSE = directionless brief nudge (e.g. "jaldi aage" → FORWARD, not PULSE).

Serving over HTTPS is required for the Web Speech API to work in most browsers, so `main.py`
self-generates a TLS cert/key pair via `openssl` (`ensure_tls_cert()`) if one isn't already present.

### Marker vision (ArUco drive-to-marker)

`marker_vision.py` provides camera-based ArUco marker detection and autonomous navigation. Three
operating modes, all using the same shared `CameraStream` (single webcam owner):

- **MarkerNavigator** — one-shot drive-to-marker: center on marker, approach, stop at standoff.
- **MarkerFollower** — continuous follow-me: track a specific marker and maintain a set distance.
- **WaypointAutopilot** — visit a sequence of marker IDs in order.

Distance is computed via the pinhole model (`marker_size_mm * focal_px / pixel_width`) — no full
camera calibration needed. `focal_px` must be measured per camera/resolution; run
`python3 marker_vision.py calibrate` once (defaults: 100mm marker at 500mm).

Tunables live in `robot_config.json` under `"vision"` (gains `kw`/`kv`, motor floors, standoff
distance, etc.). The `/video_feed` endpoint serves an always-on MJPEG stream with detection overlay.

### Odometry map server (companion process)

`start_odometry_server()` launches `odometry_locomization/run_linux.py` as a separate subprocess
(Flask app on port 5000) alongside the main controller. `main.py` proxies its endpoints
(`/state`, `/zero_yaw`, `/reset_map`, `/set_counts_per_cm`) so the browser talks to one origin.
Also provides closed-loop `move_distance_cm()` using cumulative mouse-sensor distance as feedback.

### Networking / onboarding UX

`main.py` handles Wi-Fi vs. hotspot mode setup (`enable-wifi-hotspot.sh`), QR-code generation
for easy phone pairing, and a large set of captive-portal detection routes (Android `/generate_204`,
Apple `/hotspot-detect.html`, Windows `/ncsi.txt`, etc.) plus a catch-all route — all returning the
same `CAPTIVE_PORTAL_HTML` — so that connecting to the robot's hotspot triggers an automatic
"sign-in" popup on phones that redirects to the controller UI.

### Key WebSocket messages (browser → board)

The `/ws` endpoint is the primary control channel. Messages are JSON objects; relevant keys:

| Key | Effect |
|-----|--------|
| `throttle` | Forward/backward speed (-100..100) |
| `dir_x`, `dir_y` | Strafe direction (mecanum) / steering factor (differential) |
| `dir_rot` | Rotation speed (-100..100) |
| `mode` | Mode switch: `locked`, `controller`, `hybrid`, `follow-me`, `autopilot` |
| `max_speed` | Set GUI speed limit (0..100) |
| `voice_text` | Transcribed speech → intent classifier |
| `vision_nav` | `"start"` / `"stop"` marker navigation |
| `follow` | `"start"` / `"stop"` marker following |
| `autopilot` | `"start"` / `"stop"` waypoint autopilot |
| `move_cm` | Closed-loop move-by-distance (uses odometry feedback) |

### Directory map

- `applications/web-app/` — the FastAPI application (main.py, drive modules, motor drivers,
  sensor drivers, static frontend, marker vision).
- `intent_classifier/` — ONNX voice-intent model + training/export pipeline. `infer.py`
  (production), `test_intent.py` (58 pytest tests — runnable off-board), `mobile_code.py`
  (multi-command splitting).
- `odometry_locomization/` — standalone Flask mouse-odometry map server + IMU/gyro utilities.
  `run_linux.py` on the board; `run_windows.py`/`calibrate.py` for dev-machine testing.
- `x-linux-msp1/` — sibling sensor-platform package (MSP1 expansion board), independent codebase.
- `kernel/` — prebuilt device tree sources/blobs, for reference/patching, not built here.
- `tests/` — manual hardware bring-up scripts run on the board (see `tests/README.md`).
- `scripts/deploy_starter_package.sh` — deploys `applications/` to a board over the network.
- `board_pin_mapping.md` — GPIO pinout / solder-bridge reference for the expansion board.
- `x_excluded/` — legacy demo-launcher code and project notes, not part of the active app.

## Notes for future changes

- Motor/network code paths (GPIO, PWM, hotspot control) only execute meaningfully on the actual
  board; there's no simulation harness in this repo, so changes here can't be verified by running
  locally — reason through the code and, where possible, ask the user to test on hardware.
- `robot_config.json` (drive_type, network_mode, vision tunables) is generated at runtime on the
  board and is not checked into the repo.
