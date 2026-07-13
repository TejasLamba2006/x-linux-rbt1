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

## Workflow (see AGENTS.md for full detail)

1. Edit files locally in this repo.
2. Commit and push to GitHub.
3. On the board: `cd /usr/local/x-linux-rbt1 && git pull`, or `rsync -avz applications/web-app/ root@<board-ip>:/usr/local/x-linux-rbt1/` for a quick iteration.
4. Run on the board: `python3 main.py --auto` (uses saved `robot_config.json`; omit `--auto` for the interactive CLI menu).

Useful `main.py` flags: `--auto`, `--install-service` / `--uninstall-service` / `--generate-service` (systemd unit management).

Known board-side gotchas (see AGENTS.md "Known Issues" for the full list): PWM channels can get
stuck after a crash and must be unexported via sysfs before restart; `netifaces` must come from
`apt-get`, not pip, on Yocto; pin `pydantic<2.12` (zoneinfo issue on Yocto's Python); voice control
needs `onnxruntime` and a working `openssl` (for the self-signed TLS cert) or it silently disables
itself; the odometry map server needs `flask`.

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
  expose a common interface: `parser(json_dict)`, `release()`.
- When adding motor logic, mirror this dispatch pattern rather than special-casing board/drive-type
  checks inline elsewhere — `main.py` and the frontend are meant to stay agnostic to which is active.

### Runtime data flow

1. Browser opens `/static/index.html`, connects to `/ws` (WebSocket).
2. `static/js/script.js` samples joystick/dial state every 200ms and sends JSON like
   `{"throttle": ...}`, `{"dir_x": ..., "dir_y": ...}`, `{"dir_rot": ...}`, `{"mode": ...}`.
3. `main.py`'s `ConnectionManager.receive_and_process` parses each JSON line and forwards it to
   `motor_api.parser(parsed_data)`.
4. The active drive module (`mechanumapi.py` / `normalwheelapi.py`) interprets `mode` (locked /
   controller / follow-me / autopilot — only `controller` mode currently acts on throttle/dir
   commands) and computes per-wheel PWM duty/direction, calling into the board-specific `STSPIN`
   module.
5. A background thread (`tof_obstacle_detection`) polls the VL53L5CX ToF sensor
   (`vl53l5cx/vl53l5cx.py`) and force-zeroes throttle if an obstacle is closer than 20mm.

### Voice control (optional, lazily loaded)

`main.py` adds `intent_classifier/` to `sys.path` and tries to import it at startup; if the ONNX
model or `onnxruntime` is unavailable, `INTENT_AVAILABLE` is `False` and voice control is silently
disabled — everything else still runs. The browser transcribes speech client-side (Web Speech API)
and sends `{"voice_text": ...}` over the WebSocket; `handle_voice_command()` classifies it with
`intent_classifier/robot_intent_5.onnx` and pulse-drives the active drive module's throttle/dir/rotate
functions directly (bypassing the controller/hybrid mode gate — works in any mode except `locked`).
Serving over HTTPS is required for the Web Speech API to work in most browsers, so `main.py`
self-generates a TLS cert/key pair via `openssl` (`ensure_tls_cert()`) if one isn't already present.

### Odometry map server (companion process)

`start_odometry_server()` launches `odometry_locomization/run_linux.py` as a separate subprocess
(Flask app on port 5000) alongside the main controller, for live mouse-sensor-based position
tracking/mapping. Best-effort like ToF: if the script or its sensor is missing, the main controller
still runs fine without it. Terminated via `stop_odometry_server()` on shutdown.

### Networking / onboarding UX

`main.py` also handles Wi-Fi vs. hotspot mode setup (`enable-wifi-hotspot.sh`), QR-code generation
for easy phone pairing, and a large set of captive-portal detection routes (Android `/generate_204`,
Apple `/hotspot-detect.html`, Windows `/ncsi.txt`, etc.) plus a catch-all route — all returning the
same `CAPTIVE_PORTAL_HTML` — so that connecting to the robot's hotspot triggers an automatic
"sign-in" popup on phones that redirects to the controller UI.

### Directory map

- `applications/web-app/` — the actual running application (see above).
- `intent_classifier/` — ONNX voice-intent model (`robot_intent_5.onnx`) + `infer.py`, imported
  lazily by `main.py` for voice control (see above).
- `odometry_locomization/` — standalone Flask mouse-odometry map server, launched as a companion
  subprocess by `main.py` (`run_linux.py` on the board; `run_windows.py`/`calibrate.py` for
  dev-machine testing/calibration).
- `kernel/` — prebuilt device tree sources/blobs per kernel version, for reference/patching, not built here.
- `tests/` — manual hardware bring-up test scripts (`rbt01_test.sh`, `motor_test.py`, `led_test.py`) run directly on the board; see `tests/README.md` for the full manual test procedure using a Discovery Kit.
- `scripts/deploy_starter_package.sh` — deploys the `applications/` folder to a board over the network.
- `board_pin_mapping.md` — GPIO header pinout / solder-bridge reference for the expansion board.
- `x_excluded/` — legacy/prior demo-launcher code and project-info notes (specs, todo, release checklist), kept for reference but not part of the active app.
- `GitHub/` — community health files (CONTRIBUTING, CODE_OF_CONDUCT, SECURITY).

## Notes for future changes

- Motor/network code paths (GPIO, PWM, hotspot control) only execute meaningfully on the actual
  board; there's no simulation harness in this repo, so changes here can't be verified by running
  locally — reason through the code and, where possible, ask the user to test on hardware.
- `robot_config.json` (drive_type, network_mode) is generated at runtime on the board and is not
  checked into the repo.
