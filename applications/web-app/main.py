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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import netifaces
import qrcode

# =============================================================================
# CONFIGURATION
# =============================================================================
PORT = 8000
LOG_LEVEL = logging.INFO
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "robot_config.json")
SERVICE_NAME = "x-linux-rbt1"
SERVICE_FILE = os.path.join(SCRIPT_DIR, f"{SERVICE_NAME}.service")


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
                        
                        # Process motor commands
                        if motor_api:
                            motor_api.parser(parsed_data)
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
        link_ip = f"http://{server_address}/static/index.html"
        link_hostname = f"http://{hotspot_hostname}.local:{PORT}/static/index.html"
        
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

        ip_link = f"http://{ip_address}:{PORT}/static/index.html"
        
        print(f"\n" + "=" * 70)
        print("   🚀 SERVER RUNNING - CONNECTION OPTIONS")
        print("=" * 70)
        print("")
        print("   ┌────────────────────────────────────────────────────────────┐")
        print(f"   │  📍 IP Address:   http://{ip_address}:{PORT:<27} │")
        
        hostname_link = None
        if effective_hostname:
            hostname_link = f"http://{effective_hostname}.local:{PORT}/static/index.html"
            print(f"   │  🏷️  Hostname:     http://{effective_hostname}.local:{PORT:<17} │")
        else:
            print(f"   │  🏷️  Hostname:     (Not available)                          │")
            
        print("   └────────────────────────────────────────────────────────────┘")
        print("")
        print("   📱 Access the Web App:")
        print(f"      → {ip_link}")
        if hostname_link:
            print(f"      → {hostname_link}")
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
    logger.info(f"Starting server on port {PORT}...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
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

