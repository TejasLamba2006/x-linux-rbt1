# application/web-app/main.py
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn
import netifaces
import qrcode
import os
import time
import mechanum_api as motor_api
from vl53l5cx.vl53l5cx import VL53L5CX
import threading

def show_introduction():
    # Print introduction
    print("=" * 50)
    print("Welcome to the X-LINUX-RBT1 Software Package!")
    print("Developed for the X-STM32MP-RBT01 expansion board.")
    print("=" * 50)
    print("\nSelect the mode you want to use:")
    print("1. Wi-Fi Mode")
    print("2. Hotspot Mode")




driver = VL53L5CX()

alive = driver.is_alive()
if not alive:
    raise IOError("VL53L5CX Device is not alive")

t = time.time()
driver.init()


driver.start_ranging()

previous_time = 0
loop = 1
def tof():
    if driver.check_data_ready():
        ranging_data = driver.get_ranging_data()
        now = time.time()
        if previous_time != 0:
            time_to_get_new_data = now - previous_time
        zone = 7
        Distance = ranging_data.distance_mm[driver.nb_target_per_zone * zone]
        if Distance < 30 :
            # motor_api.throttle(1)
            print(Distance)
        previous_time = now

    time.sleep(0.005)


def get_user_choice():
    # Prompt user for choice
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









def generate_qr_code(data):
    try:
        qr = qrcode.QRCode(
            version=1,  # Controls the size of the QR Code
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,  # Size of each box in the QR Code
            border=4,  # Thickness of the border
        )
        qr.add_data(data)
        qr.make(fit=True)
        qr.print_ascii()  # Prints the QR code in the terminal
    except Exception as e:
        print(f"Failed to generate QR Code: {e}")


PORT = 8000

def get_wlan0_address():
    interface = "wlan0"
    try:
        addresses = netifaces.ifaddresses(interface)
        # Get the IPv4 address of wlan0
        inet = addresses.get(netifaces.AF_INET)
        if inet:
            ip_address = inet[0]['addr']
            # Combine IP and port into a single variable
            wlan0_address = f"{ip_address}:{PORT}"
            return wlan0_address
        else:
            return "No IPv4 address found for wlan0."
    except ValueError:
        return "wlan0 interface not found on this system."
    except Exception as e:
        return f"An error occurred: {e}"


app = FastAPI()


# Serve the static files from same backend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get():
    return StaticFiles(directory="static", html=True)

# WebSocket connection manager
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
                # print(f"Received: {data}")
                json_strings = data.strip().split('\n')
                for json_string in json_strings:
                    try:
        # Parse the JSON string into a dictionary
                        parsed_data = json.loads(json_string)
                        motor_api.parser(parsed_data)  
                        # print(parsed_data)
                    except json.JSONDecodeError as e:
                        print(f"Failed to decode JSON: {e}")
                
        except WebSocketDisconnect:
            self.disconnect(websocket)
            

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await manager.receive(websocket)

if __name__ == "__main__":

    show_introduction()
    mode = get_user_choice()
    print(f"\nYou have selected: {mode}.")

    if mode == "Hotspot Mode":
        os.system("chmod +x st-hotspot-wifi-service.sh && ./st-hotspot-wifi-service.sh")
        print("Initializing the selected mode... Please wait.") 
        print("Connect to the Hotspot") 
        print("" )
        print("SSID=RBT01Demo" )
        print("PASSWORD=122345678")
        print("" )
    else:
        print("Initializing the selected mode... Please wait.")
    
    
    
    
    wlan0_address = get_wlan0_address()
    print(f"wlan0 Address: {wlan0_address}")
    
    
    if wlan0_address:
        link = f"http://{wlan0_address}"  # Create a link with the address
        print(f"Link: {link}")
        print("QR Code:")
        generate_qr_code(link)
    else:
        print("Could not retrieve wlan0 address.")
    
    collision_detect = threading.Thread(target=my_function)
    collision_detect.start()

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
    motor_api.release()

