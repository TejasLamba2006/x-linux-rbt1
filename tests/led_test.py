import time
import gpiod
from gpiod.line import Direction, Value

led_1 = 5
led_2= 5
led_3= 2
led_4= 3
led_5= 4

request =  gpiod.request_lines(
    "/dev/gpiochip5",
    consumer="blink-example",
    config={
        led_1: gpiod.LineSettings(
            direction=Direction.OUTPUT, output_value=Value.ACTIVE
        ),
        led_4: gpiod.LineSettings(
            direction=Direction.OUTPUT, output_value=Value.ACTIVE
        ),
        led_5: gpiod.LineSettings(
            direction=Direction.OUTPUT, output_value=Value.ACTIVE
        ),
        
        
    },
)
request_2 =  gpiod.request_lines(
    "/dev/gpiochip6",
    consumer="blink-example",
    config={
        led_3: gpiod.LineSettings(
            direction=Direction.OUTPUT, output_value=Value.ACTIVE
        ),       
        
    },
)
request_3 =  gpiod.request_lines(
    "/dev/gpiochip8",
    consumer="blink-example",
    config={
        led_2: gpiod.LineSettings(
            direction=Direction.OUTPUT, output_value=Value.ACTIVE
        ),       
        
    },
)


i=0
led_count = 0

while i<1:

    request.set_value(led_1, Value.INACTIVE)
    input_1 = input("LED_1 is on?(Enter Y/N)")
    if input_1 == "Y":
        led_count = led_count+1
        
    
    request.set_value(led_1, Value.ACTIVE)
    time.sleep(0.5)
    request_3.set_value(led_2, Value.INACTIVE)    
    input_2 = input("LED_2 is on?(Enter Y/N)")
    if input_2 == "Y":
        led_count = led_count+1
        
    
    request_3.set_value(led_2, Value.ACTIVE)    
    time.sleep(0.5)
    
    request_2.set_value(led_3, Value.INACTIVE)
    input_3 = input("LED_3 is on?(Enter Y/N)")
    if input_3 == "Y":
        led_count = led_count+1
        
    
    request_2.set_value(led_3, Value.ACTIVE)
    time.sleep(0.5)
    
    request.set_value(led_4, Value.INACTIVE)
    input_4 = input("LED_4 is on?(Enter Y/N)")
    if input_4 == "Y":
        led_count = led_count+1
        
    
    request.set_value(led_4, Value.ACTIVE)
    time.sleep(0.5)
    
    request.set_value(led_5, Value.INACTIVE)
    input_5 = input("LED_5 is on?(Enter Y/N)")
    if input_5 == "Y":
        led_count = led_count+1
        
    

    request.set_value(led_5, Value.ACTIVE)


    i=i+1
    