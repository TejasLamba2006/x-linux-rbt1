#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

# application/web-app/main.py

"""
X-LINUX-RBT1 Demo Application
Main entry point for the robotics control web application.

Features:
- WebSocket-based real-time motor control
- Support for Mecanum and Differential drive types
- VL53L5CX ToF sensor for obstacle detection
- QR code for easy mobile connection
"""

import asyncio
import json
import os
import sys
import time
import signal
import logging
import threading
import select
import shutil
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import uvicorn
import netifaces
import qrcode

# =============================================================================
# CONFIGURATION
# =============================================================================
PORT = 8000
LOG_LEVEL = logging.INFO
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if not os.path.isdir(os.path.join(REPO_ROOT, "odometry_locomization")):
    REPO_ROOT = SCRIPT_DIR
CONFIG_FILE = os.path.join(SCRIPT_DIR, "robot_config.json")
SERVICE_NAME = "x-linux-rbt1"
SERVICE_FILE = os.path.join(SCRIPT_DIR, f"{SERVICE_NAME}.service")
TLS_CERT_FILE = os.path.join(SCRIPT_DIR, "tls_cert.pem")
TLS_KEY_FILE = os.path.join(SCRIPT_DIR, "tls_key.pem")

# =============================================================================
# VOICE / INTENT CLASSIFICATION (optional -- see handle_voice_command)
# =============================================================================
VOICE_SPEED = 60             # duty for pulsed voice-driven moves, -100..100
VOICE_BASE_DURATION = 0.8    # seconds for a bare command with no numeric value
VOICE_PER_UNIT_DURATION = 0.15
VOICE_MAX_DURATION = 5.0

# =============================================================================
# CLOSED-LOOP MOVE-BY-DISTANCE (see move_distance_cm) -- uses the odometry
# subprocess's cumulative mouse-based distance reading as feedback.
# =============================================================================
MOVE_SPEED = 50               # duty for move_cm driving, 0..100
MOVE_MAX_CM = 500             # sanity cap on a single move_cm request
MOVE_POLL_INTERVAL = 0.1      # seconds between odometry distance polls
MOVE_TIMEOUT_PER_CM = 0.5     # worst-case seconds/cm before aborting as stuck
MOVE_TIMEOUT_MIN = 3.0
move_in_progress = False

# GUI-configurable overall speed limit (0..100), applied to joystick input
# before it reaches the drive module. Set via {"max_speed": N} over the WS.
max_speed_percent = 100


def apply_speed_limit(parsed_data: dict) -> None:
    """Scale throttle/dir_x/dir_y/dir_rot in-place by max_speed_percent,
    ahead of the drive-type-agnostic parser call, so the limit applies
    regardless of which drive module (mecanum/differential) is active."""
    if max_speed_percent >= 100:
        return
    scale = max_speed_percent / 100.0
    for key in ("throttle", "dir_x", "dir_y", "dir_rot"):
        if key in parsed_data and isinstance(parsed_data[key], (int, float)):
            parsed_data[key] = parsed_data[key] * scale

INTENT_AVAILABLE = False
try:
    sys.path.insert(0, os.path.join(REPO_ROOT, "intent_classifier"))
    from infer import classify_single_command
    INTENT_AVAILABLE = True
except Exception as e:
    logging.getLogger(__name__).warning(f"Intent classifier unavailable: {e}")


# =============================================================================
# CONFIGURATION FILE MANAGEMENT
# =============================================================================
def load_config() -> dict:
    """Load configuration from JSON file."""
    default_config = {
        "drive_type": "mecanum",
        "network_mode": "wifi"
    }
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                logger.info(f"✓ Configuration loaded from: {CONFIG_FILE}")
                return config
        else:
            logger.info("No configuration file found. Using defaults.")
            return default_config
    except Exception as e:
        logger.warning(f"Error loading config: {e}. Using defaults.")
        return default_config


def save_config(config: dict) -> bool:
    """Save configuration to JSON file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info(f"✓ Configuration saved to: {CONFIG_FILE}")
        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


def timed_input(prompt: str, timeout: int = 10) -> Optional[str]:
    """
    Get user input with a timeout.
    
    Args:
        prompt: The prompt to display
        timeout: Timeout in seconds
        
    Returns:
        User input string or None if timeout
    """
    print(prompt, end='', flush=True)
    
    # Countdown display
    import sys
    import select
    
    start_time = time.time()
    remaining = timeout
    
    while remaining > 0:
        # Check if input is available
        ready, _, _ = select.select([sys.stdin], [], [], 1)
        
        if ready:
            user_input = sys.stdin.readline().strip()
            return user_input
        
        elapsed = time.time() - start_time
        remaining = timeout - int(elapsed)
        
        # Update countdown on same line
        print(f"\r{prompt} ({remaining}s remaining): ", end='', flush=True)
    
    print()  # New line after timeout
    return None


def display_saved_config(config: dict) -> None:
    """Display the saved configuration."""
    print("\n" + "=" * 50)
    print("   📋 SAVED CONFIGURATION")
    print("=" * 50)
    print(f"\n   Drive Type:   {config.get('drive_type', 'mecanum').upper()}")
    
    drive_desc = "Omnidirectional" if config.get('drive_type') == 'mecanum' else "Standard 4-wheel"
    print(f"                 ({drive_desc})")
    
    print(f"\n   Network Mode: {config.get('network_mode', 'wifi').upper()}")
    
    mode_desc = "Connects to existing Wi-Fi" if config.get('network_mode') == 'wifi' else "Creates hotspot"
    print(f"                 ({mode_desc})")
    print("=" * 50 + "\n")


# =============================================================================
# SYSTEMD SERVICE FILE GENERATION
# =============================================================================
def generate_service_file() -> str:
    """Generate the content of a systemd service file."""
    python_path = sys.executable
    script_path = os.path.abspath(__file__)
    working_dir = SCRIPT_DIR
    hotspot_script = os.path.join(SCRIPT_DIR, "enable-wifi-hotspot.sh")
    
    # Check the saved config to determine if hotspot mode is configured
    config = load_config()
    network_mode = config.get('network_mode', 'wifi')
    
    if network_mode == "hotspot":
        # Hotspot mode - need to conflict with WiFi services and start them BEFORE us
        # so we can kill them properly
        service_content = f"""[Unit]
Description=X-LINUX-RBT1 Robot Controller Web Application (Hotspot Mode)
# Wait for basic network stack and WiFi services to initialize
After=network.target network-online.target wpa_supplicant.service NetworkManager.service
# We want network to be available but will take over the interface
Wants=network-online.target
# Conflict with normal WiFi client operation
Conflicts=wpa_supplicant.service

[Service]
Type=simple
User=root
WorkingDirectory={working_dir}
# Stop WiFi client services before starting (they may restart, but we'll kill them in the script)
ExecStartPre=/bin/sleep 5
ExecStartPre=-/bin/systemctl stop wpa_supplicant.service
ExecStartPre=-/bin/systemctl stop NetworkManager.service
ExecStartPre=/bin/sleep 2
ExecStart={python_path} {script_path} --auto
# Stop hotspot cleanly on shutdown
ExecStopPost=-{hotspot_script} stop
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""
    else:
        # WiFi mode - standard service, wait for network
        service_content = f"""[Unit]
Description=X-LINUX-RBT1 Robot Controller Web Application
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory={working_dir}
# Small delay to ensure network is fully ready
ExecStartPre=/bin/sleep 3
ExecStart={python_path} {script_path} --auto
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""
    return service_content


def create_service_file() -> bool:
    """Create the .service file in the application directory."""
    try:
        service_content = generate_service_file()
        
        with open(SERVICE_FILE, 'w') as f:
            f.write(service_content)
        
        print(f"\n✓ Service file created: {SERVICE_FILE}")
        return True
    except Exception as e:
        print(f"\n✗ Failed to create service file: {e}")
        return False


def install_service() -> bool:
    """
    Copy the service file to systemd and enable it.
    Requires root privileges.
    """
    import subprocess
    
    systemd_path = f"/etc/systemd/system/{SERVICE_NAME}.service"
    
    # Check if we have root privileges
    if os.geteuid() != 0:
        print("\n⚠  Root privileges required to install service.")
        print("   Run with: sudo python3 main.py --install-service")
        return False
    
    try:
        # Create service file first
        if not os.path.exists(SERVICE_FILE):
            if not create_service_file():
                return False
        
        # Copy to systemd
        shutil.copy(SERVICE_FILE, systemd_path)
        print(f"✓ Service file copied to: {systemd_path}")
        
        # Reload systemd daemon
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        print("✓ Systemd daemon reloaded")
        
        # Enable the service
        subprocess.run(["systemctl", "enable", SERVICE_NAME], check=True)
        print(f"✓ Service '{SERVICE_NAME}' enabled for startup")
        
        print("\n" + "=" * 50)
        print("   🎉 SERVICE INSTALLED SUCCESSFULLY!")
        print("=" * 50)
        print("\n   Commands to manage the service:")
        print(f"   • Start:   sudo systemctl start {SERVICE_NAME}")
        print(f"   • Stop:    sudo systemctl stop {SERVICE_NAME}")
        print(f"   • Status:  sudo systemctl status {SERVICE_NAME}")
        print(f"   • Logs:    sudo journalctl -u {SERVICE_NAME} -f")
        print(f"   • Disable: sudo systemctl disable {SERVICE_NAME}")
        print("=" * 50 + "\n")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Failed to install service: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Error installing service: {e}")
        return False


def uninstall_service() -> bool:
    """
    Stop and remove the service from systemd.
    Requires root privileges.
    """
    import subprocess
    
    systemd_path = f"/etc/systemd/system/{SERVICE_NAME}.service"
    
    # Check if we have root privileges
    if os.geteuid() != 0:
        print("\n⚠  Root privileges required to uninstall service.")
        print("   Run with: sudo python3 main.py --uninstall-service")
        return False
    
    try:
        # Stop the service if running
        subprocess.run(["systemctl", "stop", SERVICE_NAME], check=False)
        print(f"✓ Service '{SERVICE_NAME}' stopped")
        
        # Disable the service
        subprocess.run(["systemctl", "disable", SERVICE_NAME], check=False)
        print(f"✓ Service '{SERVICE_NAME}' disabled")
        
        # Remove the service file
        if os.path.exists(systemd_path):
            os.remove(systemd_path)
            print(f"✓ Service file removed: {systemd_path}")
        
        # Reload systemd daemon
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        print("✓ Systemd daemon reloaded")
        
        print("\n✓ Service uninstalled successfully!\n")
        return True
        
    except Exception as e:
        print(f"\n✗ Error uninstalling service: {e}")
        return False


def show_service_menu() -> None:
    """Display the service management menu."""
    print("\n" + "=" * 50)
    print("   ⚙️  SERVICE MANAGEMENT")
    print("=" * 50)
    print("\n   1. Generate .service file only")
    print("   2. Install service (enable on startup)")
    print("   3. Uninstall service")
    print("   4. Back to main menu")
    print("")
    
    while True:
        try:
            choice = int(input("   Enter your choice (1-4): "))
            if choice == 1:
                create_service_file()
                break
            elif choice == 2:
                install_service()
                break
            elif choice == 3:
                uninstall_service()
                break
            elif choice == 4:
                break
            else:
                print("   Invalid choice. Please enter 1-4.")
        except ValueError:
            print("   Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\n")
            break

# =============================================================================
# LOGGING SETUP
# =============================================================================
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# =============================================================================
# GLOBAL STATE
# =============================================================================
motor_api = None
current_drive_type: str = "unknown"
tof_driver = None
shutdown_event = threading.Event()
motor_released = False  # Flag to prevent double release
odometry_process = None  # Companion odometry-map server subprocess (see start_odometry_server)


def cleanup_motor_api() -> None:
    """Safely release motor API resources (prevents double release)."""
    global motor_released
    if motor_api and not motor_released:
        try:
            motor_api.release()
            motor_released = True
            logger.info("Motor API released")
        except Exception:
            pass  # Silently ignore cleanup errors


def start_odometry_server() -> None:
    """Launch the mouse-odometry map server (odometry_locomization/run_linux.py)
    as a companion background process alongside the main controller, so the
    live map is collecting data for the whole session. Best-effort: if the
    script or its sensor isn't available, the main controller still runs fine
    without it (matches init_tof_sensor()'s "optional" pattern below)."""
    global odometry_process
    import subprocess

    odometry_script = os.path.join(REPO_ROOT, "odometry_locomization", "run_linux.py")

    if not os.path.isfile(odometry_script):
        logger.warning(f"Odometry map server not found at {odometry_script}, skipping.")
        return

    try:
        odometry_process = subprocess.Popen(
            [sys.executable, odometry_script],
            cwd=os.path.dirname(odometry_script),
        )
        logger.info(f"Odometry map server started (pid={odometry_process.pid}, port 5000)")
    except Exception as e:
        logger.warning(f"Failed to start odometry map server: {e}")
        odometry_process = None


def stop_odometry_server() -> None:
    """Terminate the companion odometry map server, if running (prevents orphaned process)."""
    global odometry_process
    if odometry_process and odometry_process.poll() is None:
        try:
            odometry_process.terminate()
            odometry_process.wait(timeout=3)
        except Exception:
            try:
                odometry_process.kill()
            except Exception:
                pass
        finally:
            logger.info("Odometry map server stopped")
    odometry_process = None


def handle_voice_command(text: str) -> dict:
    """
    Classify a transcribed voice command (text already recognized client-side
    via the browser's Web Speech API) and pulse-drive the robot accordingly.

    Voice commands act directly on the active drive module's throttle/
    direction/rotate functions (bypassing mode_select's controller/hybrid
    gate), so they work in any mode except 'locked' -- matching the joystick
    being the "hold to move" analog, and voice being the "say it once" pulse.
    """
    if not INTENT_AVAILABLE:
        return {"error": "voice control unavailable (intent classifier not loaded)"}
    if motor_api is None:
        return {"error": "motor API not initialized"}
    if getattr(motor_api.state, "active_mode", "locked") == "locked":
        return {"intent": None, "note": "locked"}

    result = classify_single_command(text)
    intent, value = result["intent"], result["value"]
    confidence = result["confidence"]

    VOICE_CONFIDENCE_THRESHOLD = 0.6

    if intent == "NOP" or confidence < VOICE_CONFIDENCE_THRESHOLD:
        return {"intent": intent, "value": value, "confidence": confidence,
                "note": "nop" if intent == "NOP" else "low confidence"}

    if intent == "STOP":
        motor_api.stop()
        set_odometry_recording(False)
        return {"intent": intent, "value": value, "confidence": confidence}

    voice_speed = VOICE_SPEED * max_speed_percent / 100.0

    if intent == "PULSE":
        drive = {"throttle": voice_speed * 0.6}
    else:
        drive = {
            "FORWARD":      {"throttle": voice_speed},
            "BACKWARD":     {"throttle": -voice_speed},
            "STRAFE_LEFT":  {"dir_x": -voice_speed},
            "STRAFE_RIGHT": {"dir_x": voice_speed},
            "ROTATE_LEFT":  {"dir_rot": -voice_speed},
            "ROTATE_RIGHT": {"dir_rot": voice_speed},
        }.get(intent)

    if drive is None:
        return {"intent": intent, "value": value, "confidence": confidence,
                "note": "unrecognized intent"}

    set_odometry_recording(True)
    if "throttle" in drive:
        motor_api.throttle_value(drive["throttle"])
    if "dir_x" in drive:
        motor_api.direction(drive["dir_x"], 0)
    if "dir_rot" in drive:
        motor_api.rotate_angle(drive["dir_rot"])

    if intent == "PULSE":
        duration = VOICE_BASE_DURATION
    else:
        duration = min(VOICE_MAX_DURATION, VOICE_BASE_DURATION + value * VOICE_PER_UNIT_DURATION)

    def _stop_after(d):
        time.sleep(d)
        motor_api.stop()
        set_odometry_recording(False)

    threading.Thread(target=_stop_after, args=(duration,), daemon=True).start()

    return {"intent": intent, "value": value, "confidence": confidence,
            "duration": round(duration, 2)}


async def move_distance_cm(websocket: WebSocket, target_cm: float) -> None:
    """Closed-loop "move forward N cm", using the mouse-odometry subprocess's
    cumulative distance reading as feedback instead of an open-loop timed
    pulse (like voice commands use). Runs as a background asyncio task so it
    doesn't block the WS receive loop -- other commands (e.g. mode change)
    still get processed while this is driving.

    ponytail: no PID/deceleration ramp, just full-speed-then-stop; add a
    slow-down-near-target ramp if overshoot becomes a problem.
    """
    global move_in_progress
    if move_in_progress:
        await websocket.send_json({"move_result": {"error": "a move is already in progress"}})
        return
    if motor_api is None:
        await websocket.send_json({"move_result": {"error": "motor API not initialized"}})
        return
    if getattr(motor_api.state, "active_mode", "locked") == "locked":
        await websocket.send_json({"move_result": {"error": "locked"}})
        return

    target_cm = max(0.0, min(MOVE_MAX_CM, target_cm))
    start_state = await asyncio.to_thread(fetch_odometry_state)
    if start_state is None:
        await websocket.send_json({"move_result": {"error": "odometry data unavailable"}})
        return

    move_in_progress = True
    start_distance = start_state["distance"]
    timeout = max(MOVE_TIMEOUT_MIN, target_cm * MOVE_TIMEOUT_PER_CM)
    speed = MOVE_SPEED * max_speed_percent / 100.0
    started_at = time.time()
    moved = 0.0

    try:
        await asyncio.to_thread(set_odometry_recording, True)
        motor_api.throttle_value(speed)
        while moved < target_cm:
            if time.time() - started_at > timeout:
                await websocket.send_json({"move_result": {"error": "timed out", "moved_cm": round(moved, 1)}})
                return
            await asyncio.sleep(MOVE_POLL_INTERVAL)
            state = await asyncio.to_thread(fetch_odometry_state)
            if state is None:
                await websocket.send_json({"move_result": {"error": "odometry data unavailable", "moved_cm": round(moved, 1)}})
                return
            moved = state["distance"] - start_distance
        await websocket.send_json({"move_result": {"moved_cm": round(moved, 1)}})
    finally:
        motor_api.stop()
        await asyncio.to_thread(set_odometry_recording, False)
        move_in_progress = False


# =============================================================================
# DRIVE TYPE SELECTION
# =============================================================================
def get_drive_type_choice() -> str:
    """Prompt user to select drive type via CLI."""
    print("\n" + "=" * 50)
    print("           DRIVE TYPE SELECTION")
    print("=" * 50)
    print("\nSelect the drive type for your robot:")
    print("1. Mecanum Drive (Omnidirectional movement)")
    print("   - Supports lateral/diagonal movement")
    print("   - Right joystick controls direction in X-Y plane")
    print("")
    print("2. Differential Drive (Standard 4-wheel)")
    print("   - Standard 4-wheel drive")
    print("   - Right joystick X-axis controls steering")
    print("   - No lateral movement (strafing)")
    print("")
    
    while True:
        try:
            choice = int(input("Enter your choice (1 or 2): "))
            if choice == 1:
                return "mecanum"
            elif choice == 2:
                return "differential"
            else:
                print("Invalid choice. Please enter 1 or 2.")
        except ValueError:
            print("Invalid input. Please enter a numeric value (1 or 2).")
        except KeyboardInterrupt:
            print("\n\nExiting...")
            sys.exit(0)


def load_motor_api(drive_type: str):
    """
    Dynamically load the appropriate motor API based on drive type.
    
    Args:
        drive_type: Either 'mecanum' or 'differential'
        
    Returns:
        The loaded motor API module
    """
    global motor_api, current_drive_type
    
    try:
        if drive_type == "mecanum":
            import mechanumapi as motor_api_module
            logger.info("✓ Loaded Mecanum Drive API (Omnidirectional)")
        else:
            import normalwheelapi as motor_api_module
            logger.info("✓ Loaded Differential Drive API")
        
        motor_api = motor_api_module
        current_drive_type = drive_type
        return motor_api
        
    except ImportError as e:
        logger.error(f"Failed to import motor API: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading motor API: {e}")
        raise


# =============================================================================
# NETWORK MODE SELECTION
# =============================================================================
def get_network_mode_choice() -> str:
    """Prompt user to select network mode via CLI."""
    print("\n" + "=" * 50)
    print("Welcome to the X-LINUX-RBT1 Demo Application!")
    print("Developed for the X-STM32MP-RBT01 expansion board.")
    print("=" * 50)
    print("\n   🔌 MOTOR WIRING REFERENCE (STM32MP257)")
    print("   ┌─────────────────────────────────────────┐")
    print("   │ STSPIN948 #1, OUT_A → Front Left  (1A)  │")
    print("   │ STSPIN948 #1, OUT_B → Front Right (1B)  │")
    print("   │ STSPIN948 #2, OUT_A → Rear Left   (2A)  │")
    print("   │ STSPIN948 #2, OUT_B → Rear Right  (2B)  │")
    print("   └─────────────────────────────────────────┘")
    print("\nSelect the network mode you want to use:")
    print("1. Wi-Fi Mode")
    print("2. Hotspot Mode")
    
    while True:
        try:
            choice = int(input("\nEnter your choice (1 or 2): "))
            if choice == 1:
                return "wifi"
            elif choice == 2:
                return "hotspot"
            else:
                print("Invalid choice. Please enter 1 or 2.")
        except ValueError:
            print("Invalid input. Please enter a numeric value (1 or 2).")
        except KeyboardInterrupt:
            print("\n\nExiting...")
            sys.exit(0)


def setup_hotspot_mode() -> dict:
    """
    Configure and start the Wi-Fi hotspot.
    
    Returns:
        dict with keys: success, ssid, password, ip
    """
    import subprocess
    
    hotspot_script = os.path.join(SCRIPT_DIR, "enable-wifi-hotspot.sh")
    
    # Check if script exists
    if not os.path.exists(hotspot_script):
        logger.error(f"Hotspot script not found: {hotspot_script}")
        return {"success": False, "error": "Hotspot script not found"}
    
    # Make script executable
    os.chmod(hotspot_script, 0o755)
    
    print("\n" + "=" * 50)
    print("Starting Wi-Fi Hotspot...")
    print("=" * 50)
    
    try:
        # Run the hotspot script and capture output
        result = subprocess.run(
            [hotspot_script, "start"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout + result.stderr
        logger.debug(f"Hotspot script output: {output}")
        
        # Parse the output
        hotspot_info = {
            "success": False,
            "ssid": "RBT01Demo",
            "password": "12345678",
            "ip": "192.168.72.1",
            "hostname": None
        }
        
        for line in output.split('\n'):
            if line.startswith("HOTSPOT_STATUS="):
                status = line.split("=")[1].strip()
                hotspot_info["success"] = (status == "active")
            elif line.startswith("HOTSPOT_SSID="):
                hotspot_info["ssid"] = line.split("=")[1].strip()
            elif line.startswith("HOTSPOT_PASSWORD="):
                hotspot_info["password"] = line.split("=")[1].strip()
            elif line.startswith("HOTSPOT_IP="):
                hotspot_info["ip"] = line.split("=")[1].strip()
            elif line.startswith("HOTSPOT_HOSTNAME="):
                hotspot_info["hostname"] = line.split("=")[1].strip()
        
        if hotspot_info["success"]:
            print("\n✓ Hotspot started successfully!")
            print("\n" + "-" * 40)
            print("Connect to the Hotspot:")
            print(f"  SSID:     {hotspot_info['ssid']}")
            print(f"  PASSWORD: {hotspot_info['password']}")
            print(f"  IP:       {hotspot_info['ip']}")
            print("-" * 40)
            logger.info(f"Hotspot active: SSID={hotspot_info['ssid']}, IP={hotspot_info['ip']}")
        else:
            print("\n✗ Failed to start hotspot!")
            logger.error("Hotspot failed to start")
            
            # Try to get more info with status command
            status_result = subprocess.run(
                [hotspot_script, "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            logger.debug(f"Status check: {status_result.stdout}")
        
        return hotspot_info
        
    except subprocess.TimeoutExpired:
        logger.error("Hotspot script timed out")
        return {"success": False, "error": "Timeout starting hotspot"}
    except Exception as e:
        logger.error(f"Error starting hotspot: {e}")
        return {"success": False, "error": str(e)}


def check_hotspot_status() -> dict:
    """
    Check if the hotspot is currently active.
    
    Returns:
        dict with status information
    """
    import subprocess
    
    hotspot_script = os.path.join(SCRIPT_DIR, "enable-wifi-hotspot.sh")
    
    if not os.path.exists(hotspot_script):
        return {"active": False, "error": "Script not found"}
    
    try:
        result = subprocess.run(
            [hotspot_script, "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        output = result.stdout
        info = {"active": False}
        
        for line in output.split('\n'):
            if line.startswith("HOTSPOT_STATUS="):
                info["active"] = (line.split("=")[1].strip() == "active")
            elif line.startswith("HOTSPOT_IP="):
                info["ip"] = line.split("=")[1].strip()
        
        return info
        
    except Exception as e:
        logger.warning(f"Error checking hotspot status: {e}")
        return {"active": False, "error": str(e)}


# =============================================================================
# QR CODE & NETWORK UTILITIES
# =============================================================================
def ensure_tls_cert() -> bool:
    """
    Ensure a self-signed TLS cert/key pair exists for serving the app over
    HTTPS. Required for microphone access (getUserMedia/SpeechRecognition) --
    Chrome only allows those in a "secure context" (HTTPS or localhost), and
    phones connect over plain LAN/hotspot IPs, not localhost.

    Self-signed means each new device sees a one-time "connection not
    private" warning to click through -- there's no real CA for a device
    with no stable DNS name. Regenerated only if the files are missing.
    """
    import subprocess

    if os.path.isfile(TLS_CERT_FILE) and os.path.isfile(TLS_KEY_FILE):
        return True

    try:
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", TLS_KEY_FILE, "-out", TLS_CERT_FILE,
                "-days", "3650", "-nodes",
                "-subj", "/CN=x-linux-rbt1",
            ],
            check=True, capture_output=True, timeout=30,
        )
        logger.info("Generated self-signed TLS certificate")
        return True
    except Exception as e:
        logger.warning(f"Could not generate TLS certificate (openssl missing?): {e}")
        return False


def generate_qr_code(data: str) -> None:
    """Generate and print a QR code to the terminal."""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        qr.print_ascii()
    except Exception as e:
        logger.warning(f"Failed to generate QR Code: {e}")


def get_wlan0_address() -> Optional[str]:
    """
    Get the IPv4 address of the wlan0 interface.
    
    Returns:
        The wlan0 address with port, or None if not available
    """
    interface = "wlan0"
    try:
        addresses = netifaces.ifaddresses(interface)
        inet = addresses.get(netifaces.AF_INET)
        if inet:
            ip_address = inet[0]['addr']
            return f"{ip_address}:{PORT}"
        else:
            logger.warning("No IPv4 address found for wlan0")
            return None
    except ValueError:
        logger.warning("wlan0 interface not found")
        return None
    except Exception as e:
        logger.error(f"Error getting wlan0 address: {e}")
        return None


# =============================================================================
# TOF SENSOR (OBSTACLE DETECTION)
# =============================================================================
def init_tof_sensor():
    """Initialize the VL53L5CX ToF sensor."""
    global tof_driver
    
    try:
        from vl53l5cx.vl53l5cx import VL53L5CX
        
        tof_driver = VL53L5CX()
        
        if not tof_driver.is_alive():
            logger.warning("VL53L5CX Device is not responding")
            tof_driver = None
            return False
        
        tof_driver.init()
        tof_driver.start_ranging()
        logger.info("✓ VL53L5CX ToF sensor initialized")
        return True
        
    except Exception as e:
        logger.warning(f"ToF sensor initialization failed: {e}")
        tof_driver = None
        return False


def tof_obstacle_detection():
    """
    Background thread for ToF-based obstacle detection.
    Stops motors when an obstacle is detected within 20mm.
    """
    global tof_driver, motor_api, shutdown_event
    
    if tof_driver is None:
        return
    
    previous_time = 0
    
    while not shutdown_event.is_set():
        try:
            if tof_driver.check_data_ready():
                ranging_data = tof_driver.get_ranging_data()
                now = time.time()
                
                zone = 7
                distance = ranging_data.distance_mm[tof_driver.nb_target_per_zone * zone]
                
                if distance < 20:
                    logger.warning(f"Obstacle detected! Distance: {distance}mm. Stopping motors...")
                    if motor_api:
                        motor_api.stop()
                    
                    # Wait until obstacle is cleared
                    while not shutdown_event.is_set():
                        ranging_data = tof_driver.get_ranging_data()
                        distance = ranging_data.distance_mm[tof_driver.nb_target_per_zone * zone]
                        if distance >= 20:
                            logger.info(f"Obstacle cleared! Distance: {distance}mm")
                            break
                        time.sleep(0.1)
                
                previous_time = now
            
            time.sleep(0.005)
            
        except Exception as e:
            logger.error(f"ToF error: {e}")
            time.sleep(1)


# =============================================================================
# FASTAPI APPLICATION
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown."""
    logger.info("Application starting...")
    yield
    logger.info("Application shutting down...")
    shutdown_event.set()


app = FastAPI(
    title="X-LINUX-RBT1 Controller",
    description="Robotics control web application",
    version="1.0.0",
    lifespan=lifespan
)

# Serve static files
app.mount("/static", StaticFiles(directory=os.path.join(SCRIPT_DIR, "static")), name="static")


@app.get("/")
async def root():
    """Redirect to the main controller page."""
    return FileResponse(os.path.join(SCRIPT_DIR, "static", "index.html"))


@app.get("/api/drive-type")
async def get_drive_type():
    """API endpoint to get the current drive type."""
    return {"drive_type": current_drive_type}


ODOMETRY_HTML_FILE = os.path.join(REPO_ROOT, "odometry_locomization", "index.html")
ODOMETRY_STATE_URL = "http://127.0.0.1:5000/state"
ODOMETRY_ZERO_YAW_URL = "http://127.0.0.1:5000/zero_yaw"
ODOMETRY_SET_CPC_URL = "http://127.0.0.1:5000/set_counts_per_cm"
ODOMETRY_SET_RECORDING_URL = "http://127.0.0.1:5000/set_recording"
ODOMETRY_RESET_MAP_URL = "http://127.0.0.1:5000/reset_map"

_motor_moving = False


def set_odometry_recording(active: bool) -> None:
    """Tell the odometry subprocess whether to accumulate distance/position.
    The mouse sensor is mounted on the robot itself (nothing to click), so
    recording tracks whether the motors are actually being driven instead."""
    import urllib.request
    import urllib.error

    if odometry_process is None or odometry_process.poll() is not None:
        return
    try:
        body = json.dumps({"active": active}).encode()
        req = urllib.request.Request(ODOMETRY_SET_RECORDING_URL, data=body, method="POST",
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1) as resp:
            resp.read()
    except (urllib.error.URLError, TimeoutError):
        pass


@app.get("/map")
async def map_page():
    """Serve the odometry map as its own full page, proxied so it shares
    this app's origin (avoids https-page/http-iframe mixed-content blocking
    when embedded, see the map widget on the controller page)."""
    if not os.path.isfile(ODOMETRY_HTML_FILE):
        return HTMLResponse("<h1>Map unavailable</h1>", status_code=503)
    return FileResponse(ODOMETRY_HTML_FILE)


def fetch_odometry_state() -> Optional[dict]:
    """Fetch /state from the odometry companion subprocess. Shared by the
    /state proxy route and the move_cm closed-loop driver. Returns None if
    the subprocess isn't running or didn't respond in time."""
    import urllib.request
    import urllib.error

    if odometry_process is None or odometry_process.poll() is not None:
        return None
    try:
        with urllib.request.urlopen(ODOMETRY_STATE_URL, timeout=1) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        logger.warning(f"Odometry map proxy failed: {e}")
        return None


@app.get("/state")
async def map_state():
    """Proxy /state to the odometry companion subprocess (port 5000). The
    subprocess is best-effort (see start_odometry_server), so this returns
    a graceful "no data" response instead of erroring if it's not running."""
    data = fetch_odometry_state()
    if data is None:
        return JSONResponse({"available": False}, status_code=200)
    return JSONResponse(data)


@app.post("/zero_yaw")
async def map_zero_yaw():
    """Proxy the map's 'zero heading' button to the odometry subprocess."""
    import urllib.request
    import urllib.error

    if odometry_process is None or odometry_process.poll() is not None:
        return JSONResponse({"ok": False}, status_code=200)

    try:
        req = urllib.request.Request(ODOMETRY_ZERO_YAW_URL, method="POST")
        with urllib.request.urlopen(req, timeout=1) as resp:
            return JSONResponse(json.loads(resp.read()))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        logger.warning(f"Odometry zero-yaw proxy failed: {e}")
        return JSONResponse({"ok": False}, status_code=200)


@app.post("/reset_map")
async def map_reset():
    """Proxy the map's 'Reset Map' button to the odometry subprocess."""
    import urllib.request
    import urllib.error

    if odometry_process is None or odometry_process.poll() is not None:
        return JSONResponse({"ok": False}, status_code=200)

    try:
        req = urllib.request.Request(ODOMETRY_RESET_MAP_URL, method="POST")
        with urllib.request.urlopen(req, timeout=1) as resp:
            return JSONResponse(json.loads(resp.read()))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        logger.warning(f"Odometry reset-map proxy failed: {e}")
        return JSONResponse({"ok": False}, status_code=200)


@app.post("/calibrate_rotate")
async def calibrate_rotate():
    """Rotate robot left 5 s then right 5 s to warm up gyro before bias calibration."""
    import threading
    if motor_api is None:
        return JSONResponse({"ok": False, "error": "motor_api not ready"}, status_code=200)

    def _spin():
        try:
            logger.info("[CAL] warmup rotate left (5 s)")
            motor_api.rotate_angle(40)
            time.sleep(5)
            logger.info("[CAL] warmup rotate right (5 s)")
            motor_api.rotate_angle(-40)
            time.sleep(5)
            motor_api.stop()
            logger.info("[CAL] warmup rotation done")
        except Exception as e:
            logger.warning(f"[CAL] warmup rotation error: {e}")
            try:
                motor_api.stop()
            except Exception:
                pass

    threading.Thread(target=_spin, daemon=True).start()
    return JSONResponse({"ok": True})


@app.post("/set_counts_per_cm")
async def map_set_counts_per_cm(request: Request):
    """Proxy the map's counts-per-cm calibration input to the odometry subprocess."""
    import urllib.request
    import urllib.error

    if odometry_process is None or odometry_process.poll() is not None:
        return JSONResponse({"ok": False}, status_code=200)

    try:
        body = await request.body()
        req = urllib.request.Request(ODOMETRY_SET_CPC_URL, data=body, method="POST",
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1) as resp:
            return JSONResponse(json.loads(resp.read()))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        logger.warning(f"Odometry set-counts-per-cm proxy failed: {e}")
        return JSONResponse({"ok": False}, status_code=200)


# =============================================================================
# CAPTIVE PORTAL ENDPOINTS
# =============================================================================
# These endpoints handle automatic browser pop-up on hotspot connection.
# Different devices use different URLs to detect captive portals.

from fastapi.responses import HTMLResponse, RedirectResponse

# Captive portal redirect page HTML
# Captive portal redirect page HTML
CAPTIVE_PORTAL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>X-LINUX-RBT1 Controller</title>
    <style>
        :root {
            --primary: #4CAF50;
            --primary-hover: #45a049;
            --bg-gradient: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            --card-bg: rgba(255, 255, 255, 0.1);
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: var(--bg-gradient);
            color: white;
            text-align: center;
        }
        .container {
            background: var(--card-bg);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            border: 1px solid rgba(255, 255, 255, 0.18);
            max-width: 90%;
            width: 400px;
            animation: fadeIn 0.8s ease-out;
        }
        h1 { margin: 0 0 10px 0; font-size: 2rem; }
        p { opacity: 0.8; margin-bottom: 30px; }
        .btn {
            display: block;
            width: 100%;
            padding: 15px 0;
            margin: 10px 0;
            background: var(--primary);
            color: white;
            text-decoration: none;
            border-radius: 12px;
            font-weight: bold;
            font-size: 1.1rem;
            transition: transform 0.2s, background 0.2s;
            box-sizing: border-box;
            border: none;
            cursor: pointer;
        }
        .btn:hover { background: var(--primary-hover); transform: translateY(-2px); }
        .btn-secondary {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255,255,255,0.2);
        }
        .btn-secondary:hover { background: rgba(255, 255, 255, 0.2); }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
            margin-right: 10px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 X-LINUX-RBT1</h1>
        <p>Robot Controller Portal</p>
        
        <div id="status">
            <span class="spinner"></span> Connecting...
        </div>

        <div id="actions" style="display:none;">
            <a href="/static/index.html" class="btn">🚀 Open Controller</a>
            <!-- The hostname link will be updated by JS if possible, else hidden -->
            <a id="hostname-link" href="#" class="btn btn-secondary" style="display:none;">🔗 Open via Hostname</a>
        </div>
        
        <p style="font-size: 0.8rem; margin-top: 20px; opacity: 0.5;">
            If the page doesn't load automatically, click the button above.
        </p>
    </div>

    <script>
        // Try to auto-redirect after a short delay
        setTimeout(function() {
            document.getElementById('status').style.display = 'none';
            document.getElementById('actions').style.display = 'block';
            
            // Attempt auto-redirect to static page
            window.location.href = "/static/index.html";
        }, 2000);

        // Try to determine hostname link
        // This is a best-effort guess since we can't easily inject the variable here without templating
        // But we can try to construct it if we are on an IP
        try {
            const host = window.location.hostname;
            // logic: if we are on an IP, user might want to know the .local address
            // But from the client side, we don't know the .local name unless we fetch it.
            // For now, let's just leave the main button as relative path which works for both.
        } catch(e) { console.log(e); }
    </script>
</body>
</html>
"""

@app.get("/generate_204")
async def captive_portal_android():
    """Android captive portal detection."""
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)

@app.get("/captive-portal-api")
async def captive_portal_api():
    """RFC 8908 Captive Portal API."""
    from fastapi.responses import JSONResponse
    # Deliberately http:// even when the app is served over https:// -- OS-level
    # captive-portal mini-browsers (Android CaptivePortalLogin, iOS CNA) reject
    # self-signed certs and won't show the auto sign-in popup if this is https.
    return JSONResponse(content={
        "captive": True,
        "user-portal-url": f"http://192.168.72.1:{PORT}/captive-portal"
    })

@app.get("/captive-portal")
async def captive_portal_page():
    """Dedicated captive portal landing page."""
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)

@app.get("/gen_204")
async def captive_portal_android_alt():
    """Android captive portal detection (alternate)."""
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)

@app.get("/hotspot-detect.html")
async def captive_portal_apple():
    """Apple/iOS captive portal detection."""
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)

@app.get("/library/test/success.html")
async def captive_portal_apple_alt():
    """Apple/iOS captive portal detection (alternate)."""
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)

@app.get("/ncsi.txt")
async def captive_portal_windows():
    """Windows captive portal detection."""
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)

@app.get("/connecttest.txt")
async def captive_portal_windows_alt():
    """Windows captive portal detection (alternate)."""
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)

@app.get("/redirect")
async def captive_portal_redirect():
    """Generic captive portal redirect."""
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)

@app.get("/success.txt")
async def captive_portal_success():
    """Generic success check."""
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)

# Catch-all for any other captive portal detection
@app.get("/{path:path}")
async def catch_all(path: str):
    """Catch-all route for captive portal - redirects unknown paths to controller."""
    # Don't catch static files or websocket
    if path.startswith("static/") or path.startswith("ws") or path.startswith("api/"):
        return None
    # Return captive portal page for everything else
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)


# =============================================================================
# WEBSOCKET CONNECTION MANAGER
# =============================================================================
class ConnectionManager:
    """Manages WebSocket connections for real-time motor control."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")
        
        # Send drive type to the newly connected client
        try:
            await websocket.send_json({"drive_type": current_drive_type})
        except Exception as e:
            logger.warning(f"Failed to send drive type: {e}")
    
    def disconnect(self, websocket: WebSocket) -> None:
        """Handle WebSocket disconnection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass
    
    async def receive_and_process(self, websocket: WebSocket) -> None:
        """Receive and process messages from a WebSocket client."""
        try:
            while True:
                data = await websocket.receive_text()
                
                # Parse and process each JSON message
                json_strings = data.strip().split('\n')
                for json_string in json_strings:
                    if not json_string:
                        continue
                        
                    try:
                        parsed_data = json.loads(json_string)
                        
                        # Handle drive type request
                        if parsed_data.get('request') == 'drive_type':
                            await websocket.send_json({"drive_type": current_drive_type})
                            continue

                        # Handle voice command (text already transcribed client-side)
                        if 'voice_text' in parsed_data:
                            result = handle_voice_command(parsed_data['voice_text'])
                            await websocket.send_json({"voice_result": result})
                            continue

                        # Handle closed-loop move-by-distance requests
                        if 'move_cm' in parsed_data:
                            asyncio.create_task(move_distance_cm(websocket, float(parsed_data['move_cm'])))
                            continue

                        # Handle speed-limit slider updates from the GUI
                        if 'max_speed' in parsed_data:
                            global max_speed_percent
                            max_speed_percent = max(0, min(100, int(parsed_data['max_speed'])))
                            continue

                        # Process motor commands
                        if motor_api:
                            apply_speed_limit(parsed_data)
                            motor_api.parser(parsed_data)

                            global _motor_moving
                            moving = (
                                getattr(motor_api.state, "active_mode", "locked") in ("controller", "hybrid")
                                and any(abs(parsed_data.get(k, 0)) > 0.01
                                        for k in ("throttle", "dir_x", "dir_y", "dir_rot"))
                            )
                            if moving != _motor_moving:
                                _motor_moving = moving
                                asyncio.create_task(asyncio.to_thread(set_odometry_recording, moving))
                        else:
                            logger.warning("Motor API not initialized")
                            
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON: {e}")
                    except Exception as e:
                        logger.error(f"Error processing command: {e}")
                        
        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            self.disconnect(websocket)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time control."""
    await manager.connect(websocket)
    await manager.receive_and_process(websocket)


# =============================================================================
# SIGNAL HANDLERS
# =============================================================================
def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}. Shutting down...")
    shutdown_event.set()
    cleanup_motor_api()
    stop_odometry_server()
    sys.exit(0)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
def run_server(drive_type: str, network_mode: str) -> None:
    """Run the web server with the specified configuration."""
    global motor_api

    # Load motor API
    motor_api = load_motor_api(drive_type)
    print(f"\n✓ Drive Type: {'Mecanum (Omnidirectional)' if drive_type == 'mecanum' else 'Differential Drive'}")

    tls_ok = ensure_tls_cert()
    scheme = "https" if tls_ok else "http"
    if not tls_ok:
        print("\n⚠ Could not set up HTTPS (openssl unavailable) — voice control's")
        print("  microphone access will be blocked by the browser over plain HTTP.")

    server_address = None
    hotspot_hostname = None
    
    if network_mode == "hotspot":
        # Show connection info BEFORE starting hotspot (SSH will disconnect!)
        hotspot_ip = "192.168.72.1"
        hotspot_ssid = "RBT01Demo"
        hotspot_password = "12345678"
        hotspot_hostname = None
        
        # Try to read from /etc/default/hostapd if it exists
        try:
            import subprocess
            result = subprocess.run(
                ["sh", "-c", "source /etc/default/hostapd 2>/dev/null && echo $HOSTAPD_SSID"],
                capture_output=True, text=True
            )
            if result.stdout.strip():
                hotspot_ssid = result.stdout.strip()
            result = subprocess.run(
                ["sh", "-c", "source /etc/default/hostapd 2>/dev/null && echo $HOSTAPD_PASSWD"],
                capture_output=True, text=True
            )
            if result.stdout.strip():
                hotspot_password = result.stdout.strip()
        except:
            pass
        
        # Generate hostname from MAC address (same logic as shell script)
        try:
            with open('/sys/class/net/wlan0/address', 'r') as f:
                mac = f.read().strip()
                parts = mac.split(':')
                hotspot_hostname = f"rbt20-{parts[3]}-{parts[4]}-{parts[5]}".lower()
        except:
            hotspot_hostname = "rbt20-demo"
        
        server_address = f"{hotspot_ip}:{PORT}"
        link_ip = f"{scheme}://{server_address}/static/index.html"
        link_hostname = f"{scheme}://{hotspot_hostname}.local:{PORT}/static/index.html"
        
        # Display all info BEFORE starting hotspot
        print("\n")
        print("=" * 70)
        print("   📡 HOTSPOT MODE - CONNECTION INFO")
        print("=" * 70)
        print("")
        print("   ⚠️  IMPORTANT: SSH connection will disconnect when hotspot starts!")
        print("   📝 Save this information now:")
        print("")
        print("   ┌────────────────────────────────────────────────────────────┐")
        print(f"   │  Network (SSID):  {hotspot_ssid:<42} │")
        print(f"   │  Password:        {hotspot_password:<42} │")
        print(f"   │  Server IP:       {hotspot_ip:<42} │")
        print(f"   │  Hostname:        {hotspot_hostname + '.local':<42} │")
        print("   └────────────────────────────────────────────────────────────┘")
        print("")
        print(f"   🌐 Web App URL (IP):       {link_ip}")
        print(f"   🌐 Web App URL (Hostname): {link_hostname}")
        print("")
        print("   📱 Scan QR Code to connect (uses hostname):")
        print("")
        generate_qr_code(link_hostname)
        print("")
        print("=" * 70)
        print("   🚀 Starting hotspot in 5 seconds...")
        print("      (SSH connection will be lost)")
        print("=" * 70)
        print("")
        
        # Countdown before starting hotspot
        for i in range(5, 0, -1):
            print(f"   Starting in {i}...", end='\r')
            time.sleep(1)
        print("   Starting hotspot now!    ")
        print("")
        
        # Now start the hotspot
        hotspot_info = setup_hotspot_mode()
        
        # Update hostname from actual script output if available
        if hotspot_info.get("hostname"):
            hotspot_hostname = hotspot_info["hostname"].replace('.local', '')
        
        if not hotspot_info.get("success"):
            print("\n⚠ Hotspot failed to start. Falling back to Wi-Fi mode...")
            print("Please ensure you're connected to a network.\n")
            server_address = get_wlan0_address()
        else:
            # Use hostname-based address for server
            server_address = f"{hotspot_hostname}.local:{PORT}"
    else:
        print("\nInitializing Wi-Fi Mode... Please wait.")
        server_address = get_wlan0_address()
    
    # Initialize ToF sensor (optional)
    tof_available = init_tof_sensor()

    # Launch the odometry map server as a companion background process (optional)
    start_odometry_server()
    
    # Display connection information
    if server_address:
        # Determine IP and Hostname
        ip_address = server_address.split(':')[0]
        
        effective_hostname = None
        if network_mode == "hotspot" and hotspot_hostname:
            effective_hostname = hotspot_hostname
        else:
            try:
                import socket
                effective_hostname = socket.gethostname()
                # If hostname is just 'localhost', ignore it
                if effective_hostname == "localhost":
                    effective_hostname = None
            except:
                pass

        ip_link = f"{scheme}://{ip_address}:{PORT}/static/index.html"

        print(f"\n" + "=" * 70)
        print("   🚀 SERVER RUNNING - CONNECTION OPTIONS")
        print("=" * 70)
        print("")
        print("   ┌────────────────────────────────────────────────────────────┐")
        print(f"   │  📍 IP Address:   {scheme}://{ip_address}:{PORT:<27} │")

        hostname_link = None
        if effective_hostname:
            hostname_link = f"{scheme}://{effective_hostname}.local:{PORT}/static/index.html"
            print(f"   │  🏷️  Hostname:     {scheme}://{effective_hostname}.local:{PORT:<17} │")
        else:
            print(f"   │  🏷️  Hostname:     (Not available)                          │")
            
        print("   └────────────────────────────────────────────────────────────┘")
        print("")
        print("   📱 Access the Web App:")
        print(f"      → {ip_link}")
        if hostname_link:
            print(f"      → {hostname_link}")
        if odometry_process:
            print("")
            print("   🗺️  Odometry Map (live):")
            print(f"      → http://{ip_address}:5000/")
        print("")
        print("=" * 70)
        
        if hostname_link:
            print("   📱 Scan QR Code to connect (uses hostname):")
            print("")
            generate_qr_code(hostname_link)
        else:
            print("   📱 Scan QR Code to connect:")
            print("")
            generate_qr_code(ip_link)
            
    else:
        print("\n⚠ Could not retrieve network address.")
        print("Please check your network connection.")
    
    # Start the web server
    logger.info(f"Starting server on port {PORT} ({scheme})...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        ssl_certfile=TLS_CERT_FILE if tls_ok else None,
        ssl_keyfile=TLS_KEY_FILE if tls_ok else None,
    )


def show_main_menu() -> str:
    """Display the main menu and get user choice."""
    print("\n" + "=" * 50)
    print("   🤖 X-LINUX-RBT1 ROBOT CONTROLLER")
    print("=" * 50)
    print("\n   1. Start Robot Server")
    print("   2. Configure Settings")
    print("   3. Manage Systemd Service")
    print("   4. Exit")
    print("")
    
    while True:
        try:
            choice = input("   Enter your choice (1-4): ").strip()
            if choice in ['1', '2', '3', '4']:
                return choice
            print("   Invalid choice. Please enter 1-4.")
        except KeyboardInterrupt:
            print("\n")
            return '4'


if __name__ == "__main__":
    import argparse
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="X-LINUX-RBT1 Robot Controller")
    parser.add_argument('--auto', action='store_true', 
                        help='Automatically use saved configuration without prompts')
    parser.add_argument('--install-service', action='store_true',
                        help='Install the systemd service for startup')
    parser.add_argument('--uninstall-service', action='store_true',
                        help='Uninstall the systemd service')
    parser.add_argument('--generate-service', action='store_true',
                        help='Generate the .service file only')
    args = parser.parse_args()
    
    try:
        # Handle service-related command line arguments
        if args.generate_service:
            create_service_file()
            sys.exit(0)
        
        if args.install_service:
            install_service()
            sys.exit(0)
        
        if args.uninstall_service:
            uninstall_service()
            sys.exit(0)
        
        # Load saved configuration
        saved_config = load_config()
        
        # Auto mode - use saved config directly
        if args.auto:
            print("\n" + "=" * 50)
            print("   🤖 AUTO MODE - Using saved configuration")
            print("=" * 50)
            display_saved_config(saved_config)
            
            drive_type = saved_config.get('drive_type', 'mecanum')
            network_mode = saved_config.get('network_mode', 'wifi')
            
            run_server(drive_type, network_mode)
            sys.exit(0)
        
        # Interactive mode with config file check
        if os.path.exists(CONFIG_FILE):
            # Config file exists - ask user with timeout
            display_saved_config(saved_config)
            
            print("   Would you like to use the saved configuration?")
            print("   Press 'y' for Yes, 'n' for No, or wait 10 seconds for auto-Yes")
            print("")
            
            response = timed_input("   Your choice [Y/n]: ", timeout=10)
            
            if response is None:
                # Timeout - use config automatically
                print("\n   ⏱️  No input received. Using saved configuration automatically...")
                drive_type = saved_config.get('drive_type', 'mecanum')
                network_mode = saved_config.get('network_mode', 'wifi')
                
                run_server(drive_type, network_mode)
                sys.exit(0)
            
            elif response.lower() in ['y', 'yes', '']:
                # User confirmed - use saved config
                print("\n   ✓ Using saved configuration...")
                drive_type = saved_config.get('drive_type', 'mecanum')
                network_mode = saved_config.get('network_mode', 'wifi')
                
                run_server(drive_type, network_mode)
                sys.exit(0)
            
            # User said no - fall through to interactive menu
            print("\n   Proceeding to configuration menu...")
        
        # Main menu loop
        while True:
            choice = show_main_menu()
            
            if choice == '1':
                # Start with current/default config
                config = load_config()
                run_server(config.get('drive_type', 'mecanum'), 
                          config.get('network_mode', 'wifi'))
                break
                
            elif choice == '2':
                # Configure settings
                drive_type = get_drive_type_choice()
                network_mode = get_network_mode_choice()
                
                # Save the configuration
                new_config = {
                    'drive_type': drive_type,
                    'network_mode': network_mode
                }
                save_config(new_config)
                
                print("\n   Configuration saved! Start the controller now? [Y/n]: ", end='')
                start_now = input().strip().lower()
                
                if start_now in ['', 'y', 'yes']:
                    run_server(drive_type, network_mode)
                    break
                    
            elif choice == '3':
                # Service management
                show_service_menu()
                
            elif choice == '4':
                # Exit
                print("\n   Goodbye! 👋\n")
                break
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        shutdown_event.set()
        cleanup_motor_api()
        stop_odometry_server()

