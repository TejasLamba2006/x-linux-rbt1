#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
# BSD 3-Clause License - https://opensource.org/licenses/BSD-3-Clause

# application/web-app/main.py

PORT = 8000

import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn
import netifaces
import qrcode
import os
import time
import mechanumapi as motor_api
from vl53l5cx.vl53l5cx import VL53L5CX
import threading

# ============================== #
#         Introduction           #
# ============================== #

def show_introduction():
    print("=" * 50)
    print("Welcome to the X-LINUX-RBT1 Demo Application!")
    print("Developed for the X-STM32MP-RBT01 expansion board.")
    print("=" * 50)
    print("\nSelect the mode you want to use:")
    print("1. Wi-Fi Mode")
    print("2. Hotspot Mode")

# ============================== #
#       VL53L5CX Initialization  #
# ============================== #

driver = VL53L5CX()

if not driver.is_alive():
    raise IOError("VL53L5CX Device is not responding")

print("VL53L5CX detected.")

t = time.time()
driver.init()
driver.start_ranging()

previous_time = 0

# ============================== #
#        TOF Collision Avoidance #
# ============================== #

OBSTACLE_THRESHOLD_MM = 20
previous_time = 0
# Global variable to track obstacle status
obstacle_detected = False

def tof():
    global previous_time, obstacle_detected
    
    while True:
        if driver.check_data_ready():
            ranging_data = driver.get_ranging_data()

            # As the sensor is set in 4x4 mode by default, we have a total 
            # of 16 zones to print. For this example, only the data of first zone are printed
            now = time.time()
            
            if previous_time != 0:
                time_to_get_new_data = now - previous_time
                print(f"Print data no : {driver.streamcount: >3d} ({time_to_get_new_data * 1000:.1f}ms)")
            else:
                print(f"Print data no : {driver.streamcount: >3d}")

            # Get the distance from zone 8 (middle front)
            i = 8
            current_distance = ranging_data.distance_mm[driver.nb_target_per_zone * i]
            print(f"Distance : {current_distance: >4.0f} mm")
            
            # Check if obstacle is detected (distance less than threshold)
            if current_distance < OBSTACLE_THRESHOLD_MM:
                if not obstacle_detected:
                    print("OBSTACLE DETECTED! Stopping vehicle.")
                    # Send stop command to motors
                    stop_command = {"throttle": 0}
                    motor_api.parser(stop_command)
                    obstacle_detected = True
            else:
                # If we were in obstacle state and now it's clear
                if obstacle_detected:
                    print("Path clear, vehicle can move again.")
                    obstacle_detected = False
            
            print("")
            previous_time = now

        time.sleep(0.2)  # More frequent checks (200ms instead of 1s)
# ============================== #
#        Mode Selection          #
# ============================== #

def get_user_choice():
    while True:
        try:
            choice = int(input("\nEnter your choice (1 or 2): "))
            if choice == 1:
                return "Wi-Fi Mode"
            elif choice == 2:
                return "Hotspot Mode"
            else:
                print("Invalid choice. Please enter 1 or 2.")
        except ValueError:
            print("Invalid input. Please enter a numeric value (1 or 2).")

# ============================== #
#      QR Code Generation        #
# ============================== #

def generate_qr_code(data):
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
        print(f"Failed to generate QR Code: {e}")

# ============================== #
#   Get wlan0 IP Address         #
# ============================== #

def get_wlan0_address():
    interface = "wlan0"
    try:
        addresses = netifaces.ifaddresses(interface)
        inet = addresses.get(netifaces.AF_INET)
        if inet:
            ip_address = inet[0]['addr']
            return f"{ip_address}:{PORT}"
        else:
            return None
    except Exception as e:
        return None

# ============================== #
#        FastAPI Setup           #
# ============================== #

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get():
    return StaticFiles(directory="static", html=True)

# ============================== #
#  WebSocket Connection Manager  #
# ============================== #

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print("Client connected")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print("Client disconnected")

async def receive(self, websocket: WebSocket):
    global obstacle_detected
    try:
        while True:
            data = await websocket.receive_text()
            json_strings = data.strip().split('\n')
            for json_string in json_strings:
                try:
                    parsed_data = json.loads(json_string)
                    
                    # If obstacle detected, override any throttle commands to 0
                    if obstacle_detected:
                        # Create a copy of parsed_data with throttle set to 0
                        safe_data = {"throttle":0}
                        motor_api.parser(safe_data)
                        # Inform the client that movement is blocked
                  #      await websocket.send_text(json.dumps({"status": "blocked", "reason": "obstacle_detected"}))
                    else:
                        # Process command normally
                        motor_api.parser(parsed_data)
                except json.JSONDecodeError as e:
                    print(f"Failed to decode JSON: {e}")
    except WebSocketDisconnect:
        self.disconnect(websocket)
manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await manager.receive(websocket)

# ============================== #
#            Main                #
# ============================== #

if __name__ == "__main__":
    show_introduction()
    mode = get_user_choice()
    print(f"\nYou have selected: {mode}.")

    if mode == "Hotspot Mode":
        os.system("chmod +x st-hotspot-wifi-service.sh && ./st-hotspot-wifi-service.sh start")
        print("Initializing Hotspot Mode... Please wait.")
        print("SSID=RBT1Demo\nPASSWORD=122345678\n")
    else:
        print("Initializing Wi-Fi Mode... Please wait.")

    wlan0_address = get_wlan0_address()
    if wlan0_address:
        link = f"http://{wlan0_address}/static/index.html"  # Create a link with the address
        print(f"Link: {link}")
        print("QR Code:")
        generate_qr_code(link)
    else:
        print("Could not retrieve wlan0 address.")
    
    # Please uncomment following 2 lines to enable collision avoidance feature
    # collision_detect = threading.Thread(target=tof, daemon=True)
    # collision_detect.start()

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
    motor_api.release()
