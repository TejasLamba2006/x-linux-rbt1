
Board = "MP2"
if Board == "MP2":
    import stm32mp2 as STSPIN
elif Board == "MP1":
    import stm32mp1 as STSPIN

global active_mode
active_mode = 'locked'
global motor_1a_factor
motor_1a_factor = 1
global motor_1b_factor
motor_1b_factor = 1
global motor_2a_factor
motor_2a_factor = 1
global motor_2b_factor
motor_2b_factor = 1

def mode_select(mode):
    global active_mode
    active_mode = mode
    print(active_mode)

def throttle_value(value):
    print(value)
    if value >= 0:
        if motor_1a_factor > 0:
            STSPIN.motor_1a(value*abs(motor_1a_factor),0 )
        else:
            STSPIN.motor_1a(value*abs(motor_1a_factor),1 )

        if motor_1b_factor > 0:
            STSPIN.motor_1b(value*abs(motor_1b_factor),0 )
        else:
            STSPIN.motor_1b(value*abs(motor_1b_factor),1 )

        if motor_2a_factor > 0:
            STSPIN.motor_2a(value*abs(motor_2a_factor),0 )
        else:
            STSPIN.motor_2a(value*abs(motor_2a_factor),1 )

        if Board == "MP2":
            if motor_2b_factor > 0:
                STSPIN.motor_2b(value*abs(motor_2b_factor),1 )
            else:
                STSPIN.motor_2b(value*abs(motor_2b_factor),0 )

        else:
            if motor_2b_factor > 0:
                STSPIN.motor_2b(100-(value*abs(motor_2b_factor)),1 )
            else:
                STSPIN.motor_2b(100-(value*abs(motor_2b_factor)),0 )
        
    



    elif value < 0 :
        if motor_1a_factor > 0:
            STSPIN.motor_1a(-value*abs(motor_1a_factor),1 )
        else:
            STSPIN.motor_1a(-value*abs(motor_1a_factor),0 )

        if motor_1b_factor > 0:
            STSPIN.motor_1b(-value*abs(motor_1b_factor),1 )
        else:
            STSPIN.motor_1b(-value*abs(motor_1b_factor),0 )

        if motor_2a_factor > 0:
            STSPIN.motor_2a(-value*abs(motor_2a_factor),1 )
        else:
            STSPIN.motor_2a(-value*abs(motor_2a_factor),0 )


        if Board == "MP2":
            if motor_2b_factor > 0:
                STSPIN.motor_2b(-value*abs(motor_2b_factor),1 )
            else:
                STSPIN.motor_2b(-value*abs(motor_2b_factor),0 )

        else:
            if motor_2b_factor > 0:
                STSPIN.motor_2b(100-(-value*abs(motor_2b_factor)),1 )
            else:
                STSPIN.motor_2b(100-(-value*abs(motor_2b_factor)),0 )
        
    
def rotate_angle(angle):
    # if angle < 180:
    if angle >= 0:
        rotate_right(angle)
    elif angle < 0:
        rotate_left(abs(angle))
        print(angle)
    

def rotate_right(speed):
    STSPIN.motor_1a(speed,0 )
    STSPIN.motor_1b(speed,1 )
    STSPIN.motor_2a(speed,0 )
    STSPIN.motor_2b(100-speed,1 )

def rotate_left(speed):
    STSPIN.motor_1a(speed,1 )
    STSPIN.motor_1b(speed,0 )
    STSPIN.motor_2a(speed,1 )
    STSPIN.motor_2b(100-speed,0 )




def direction(x_axis,y_axis):
    print(f"x-axis:{x_axis}")
    print(f"y-axis:{y_axis}")
    global motor_1a_factor
    global motor_1b_factor
    global motor_2a_factor
    global motor_2b_factor
    mappedX = x_axis 
    mappedY = y_axis 
    
    v1 = mappedY + mappedX
    v2 = mappedY - mappedX
    v3 = mappedY - mappedX
    v4 = mappedY + mappedX
    
    

    v_max = max(abs(v1),abs(v2),abs(v3),abs(v4))
    if v_max > 1:
        v1 /=v_max
        v2 /=v_max
        v3 /=v_max
        v4 /=v_max
    

    motor_1a_factor = v1
    motor_1b_factor = v2
    motor_2a_factor = v3
    motor_2b_factor = v4
    print(v1)
    print(v2)
    print(v3)
    print(v4)
    if x_axis == 0 and y_axis==0:
        print(x_axis)
        print(y_axis)
        motor_1a_factor = 1
        motor_1b_factor = 1
        motor_2a_factor = 1
        motor_2b_factor = 1

    
        
    
    
    
    
    
    
    
def parser(parsed_data):
    if "mode" in parsed_data:
        mode_select(parsed_data['mode'])
        
    if active_mode == 'controller':
        # print(f"{parsed_data['mode']}")
        if "throttle" in parsed_data:
            throttle_value(parsed_data['throttle'])
        
        if "dir_rot" in parsed_data:
            rotate_angle(parsed_data['dir_rot'])
        
        if "dir_x" in parsed_data and "dir_y" in parsed_data:
            direction(parsed_data['dir_x'],parsed_data['dir_y'])
        

def release():
    STSPIN.release()
