# AGENTS.md — X-LINUX-RBT1 Development Guide

## Workflow

1. Make changes to files in this repo (local PC)
2. `git add`, `git commit`, `git push` to GitHub
3. On the board: `cd /usr/local/x-linux-rbt1 && git pull`

## Board Access

- **SSH**: `ssh root@<board-ip>` (no password by default)
- **Web App**: `http://<board-ip>:8000/static/index.html`
- **App location on board**: `/usr/local/x-linux-rbt1/`

## Deploy from Repo to Board

```bash
# From local PC — rsync the web-app folder to board
rsync -avz applications/web-app/ root@<board-ip>:/usr/local/x-linux-rbt1/
```

Or pull from GitHub on the board directly:
```bash
cd /usr/local/x-linux-rbt1
git pull origin release_v1.1
```

## Run the Application

```bash
# Kill any running instance
kill $(ps aux | grep 'main.py' | grep -v grep | awk '{print $2}')

# Unexport stuck PWM channels
echo 1 > /sys/class/pwm/pwmchip0/unexport
echo 3 > /sys/class/pwm/pwmchip0/unexport
echo 1 > /sys/class/pwm/pwmchip8/unexport
echo 0 > /sys/class/pwm/pwmchip12/unexport

# Start app
cd /usr/local/x-linux-rbt1
nohup python3 main.py --auto > /tmp/robot.log 2>&1 &
```

## View Logs

```bash
tail -f /tmp/robot.log
```

## Keyboard Controls (Desktop Browser)

| Key | Action |
|-----|--------|
| W / ↑ | Forward |
| S / ↓ | Backward |
| A / ← | Turn Left |
| D / → | Turn Right |
| Q | Rotate Left (in-place) |
| E | Rotate Right (in-place) |
| 1 | Locked mode |
| 2 | Controller mode |
| 3 | Hybrid mode |
| 4 | Follow-me mode |
| 5 | Autopilot mode |

## Known Issues

- **netifaces**: Cannot install via `pip3` on Yocto (no cross-compiler). Use `apt-get install python3-netifaces` instead.
- **zoneinfo**: Missing in Yocto Python 3.12. Use `pydantic<2.12` to avoid import errors.
- **PWM export**: After crash, PWM channels may be stuck. Unexport before restarting.
- **ISM330DHCX**: Not detected on I2C bus 1. Check board orientation or solder bridges.
- **opencv (marker vision)**: Install via `apt-get install python3-opencv`, NOT pip (same no-wheel/
  no-cross-compiler issue as netifaces). ArUco ships inside OpenCV — no extra package. If `cv2` is
  missing, vision silently disables and everything else still runs.
- **focal_px calibration**: Marker-distance accuracy depends on the camera's focal length in pixels.
  Run it once per camera/resolution: put an ArUco marker flat at a tape-measured distance and run
  `python3 marker_vision.py calibrate` (defaults: 100mm marker @ 500mm). Put the printed `focal_px`
  into `robot_config.json` under `"vision"`. Ships with a default (~900) that the ToF sensor backstops.

## Python Dependencies (on board)

```bash
apt-get install python3-gpiod python3-netifaces
pip3 install smbus2 fastapi uvicorn websockets qrcode 'pydantic<2.12' onnxruntime numpy flask
```

Marker vision (ArUco drive-to-marker): `apt-get install python3-opencv` (see Known Issues). Loaded
lazily by `main.py`; if unavailable, vision is silently disabled and everything else still works.

Voice control: `intent_classifier/robot_intent_5.onnx` runs via `onnxruntime` (loaded lazily by
`applications/web-app/main.py`; if unavailable, voice control is silently disabled and everything
else still works). `flask` is only needed for the odometry map server
(`odometry_locomization/run_linux.py`), which `main.py` also launches automatically.

