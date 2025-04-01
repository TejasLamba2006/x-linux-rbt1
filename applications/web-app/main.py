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


def tof():
    while True:
        if driver.check_data_ready():
            ranging_data = driver.get_ranging_data()

        # As the sensor is set in 4x4 mode by default, we have a total 
        # of 16 zones to print. For this example, only the data of first zone are 
        # print
        now = time.time()
        if previous_time != 0:
            time_to_get_new_data = now - previous_time
            print(f"Print data no : {driver.streamcount: >3d} ({time_to_get_new_data * 1000:.1f}ms)")
        else:
            print(f"Print data no : {driver.streamcount: >3d}")

        i = 8
        print(f"Distance : {ranging_data.distance_mm[driver.nb_target_per_zone * i]: >4.0f} mm")

        print("")

        previous_time = now
        loop += 1

    time.sleep(0.005)

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
        try:
            while True:
                data = await websocket.receive_text()
                json_strings = data.strip().split('\n')
                for json_string in json_strings:
                    try:
                        parsed_data = json.loads(json_string)
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
        link = f"http://{wlan0_address}"
        print(f"wlan0 Address: {wlan0_address}")
        print(f"Link: {link}")
        print("QR Code:")
        generate_qr_code(link)
    else:
        print("Could not retrieve wlan0 address.")

    collision_detect = threading.Thread(target=tof, daemon=True)
    collision_detect.start()

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
    motor_api.release()
