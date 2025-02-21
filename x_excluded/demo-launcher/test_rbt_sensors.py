import time
#import pwm
import os
import keyboard
import threading


exit_flag = False

def monitor_input():
    global exit_flag
    while True:
        user_input = input("Type 'x' to exit: ")
        if user_input.lower() == 'x':
            print("exit")
            exit_flag = True
            break

# Start the input monitoring thread
input_thread = threading.Thread(target=monitor_input)
input_thread.daemon = True
input_thread.start()

while not exit_flag:
    os.system("python3 vl53l5cx/examples/simple_ranging_example.py")
    time.sleep(3)
    os.system("./Sensor/ism330dhcx.sh")
    time.sleep(3)
    os.system("./Sensor/ism330dhcx.sh")
    time.sleep(3)
    


