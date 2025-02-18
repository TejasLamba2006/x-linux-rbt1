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

chip_a = "/dev/gpiochip0"
chip_b = "/dev/gpiochip1"
chip_c = "/dev/gpiochip2"
chip_d = "/dev/gpiochip3"
chip_e = "/dev/gpiochip4"
chip_f = "/dev/gpiochip5"
chip_g = "/dev/gpiochip6"
chip_h = "/dev/gpiochip7"
chip_i = "/dev/gpiochip8"


pins_1 = {
                "pwm_a": ("pwmchip0", 1),
                "pwm_b": ("pwmchip4", 1),
                "ref_a": (chip_e, "NA"),
                "ref_b": (chip_a, "NA"),
                "en_a" : (chip_d, 7),
                "en_b" : (chip_g, 15),
                "stdby": (chip_e, "NA"),
                "dir_a": (chip_f, 7),
                "dir_b": (chip_f, 6)
            }

pins_2 = {
                "pwm_a": ("pwmchip8", 1),
                "pwm_b": ("pwmchip12", 0),
                "ref_a": (chip_e, "NA"),
                "ref_b": (chip_a, "NA"),
                "en_a" : (chip_f, 1),
                "en_b" : (chip_f, 0),
                "stdby": (chip_e, "NA"),
                "dir_a": (chip_f, 9),
                "dir_b": (chip_f, 8)
            }
from Motor.evspin948_driver import EVSPIN948Driver
spn_motor_1 = EVSPIN948Driver(pins_1)
spn_motor_1.setup_gpio()

spn_motor_2 = EVSPIN948Driver(pins_2)
spn_motor_2.setup_gpio()

def forward():
    print("Forward")
    spn_motor_1.stop()
    spn_motor_2.stop()
    spn_motor_1.forward()
    spn_motor_2.forward()
    spn_motor_1.start()
    spn_motor_2.start()

def stop():
    print("stop")
    spn_motor_1.stop()
    spn_motor_2.stop()



def backward():

    spn_motor_1.stop()
    spn_motor_2.stop()

        
    spn_motor_2.backward()
    spn_motor_1.backward()
    
    
    spn_motor_1.start()
    spn_motor_2.start()
    print("Reverse")



def left():
    print("Left")
    spn_motor_1.stop()
    spn_motor_2.stop()
        
    spn_motor_1.left()
    spn_motor_2.left()
    
    spn_motor_1.start()
    spn_motor_2.start()



def on_left_arrow_release():
    
    spn_motor_1.stop()
    spn_motor_2.stop()
    




def right():
    print("Right")
    spn_motor_1.stop()
    spn_motor_2.stop()


    spn_motor_1.right()


    spn_motor_2.right()
    
    spn_motor_2.start()
    spn_motor_1.start()
    
    
    

def on_right_arrow_release():
    spn_motor_1.stop()
    spn_motor_2.stop()

def release():
    spn_motor_2.end()
    spn_motor_1.end()
    
    
    
def rampUp():
    spn_motor_1.rampUp()
    spn_motor_2.rampUp()


def rampDown():
    spn_motor_1.rampDown()
    spn_motor_2.rampDown()

def directionForward():
    spn_motor_1.forward()
    spn_motor_2.forward()

def directionBackward():
    spn_motor_1.backward()
    spn_motor_2.backward()




while not exit_flag:
    directionForward()
    rampUp()
    os.system("python3 vl53l5cx/examples/simple_ranging_example.py")
    time.sleep(5)
    rampDown()
    stop()
    time.sleep(3)
    directionBackward()
    rampUp()
    os.system("./Sensor/ism330dhcx.sh")
    time.sleep(5)
    os.system("./Sensor/ism330dhcx.sh")
    rampDown()
    stop()
    time.sleep(3)
    
spn_motor_1.end()
spn_motor_2.end()



