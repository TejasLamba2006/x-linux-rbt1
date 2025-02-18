import time
import gpiod
from gpiod.line import Direction, Value

motor_1 = 7
motor_2= 13
motor_3= 11
motor_4= 13

request =  gpiod.request_lines(
    "/dev/gpiochip2",
    consumer="blink-example",
    config={
        motor_1: gpiod.LineSettings(
            direction=Direction.OUTPUT, output_value=Value.ACTIVE
        ),
        
    },
)
request_2 =  gpiod.request_lines(
    "/dev/gpiochip3",
    consumer="blink-example",
    config={
        motor_2: gpiod.LineSettings(
            direction=Direction.OUTPUT, output_value=Value.ACTIVE
        ),       
        
    },
)
request_3 =  gpiod.request_lines(
    "/dev/gpiochip7",
    consumer="blink-example",
    config={
        motor_3: gpiod.LineSettings(
            direction=Direction.OUTPUT, output_value=Value.ACTIVE
        ),       
        
    },
)

request_4 =  gpiod.request_lines(
    "/dev/gpiochip1",
    consumer="blink-example",
    config={
        motor_4: gpiod.LineSettings(
            direction=Direction.OUTPUT, output_value=Value.ACTIVE
        ),       
        
    },
)



i=0
led_count = 0

while i<1:
    request.set_value(motor_1, Value.ACTIVE)
    request_2.set_value(motor_2, Value.ACTIVE)
    request_3.set_value(motor_3, Value.ACTIVE)
    request_4.set_value(motor_4, Value.ACTIVE)

    print("Are motors running?")
    input_1 = input()
    if input_1 == "Y":        
        request.set_value(motor_1, Value.ACTIVE)
        request_2.set_value(motor_2, Value.ACTIVE)
        request_3.set_value(motor_3, Value.ACTIVE)
        request_4.set_value(motor_4, Value.ACTIVE)
    i=i+1
