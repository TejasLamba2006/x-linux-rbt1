# Note this file is not tested properly

# Lower-level motor control function
def rover_move_ll(pwm_front_left, pwm_front_right, pwm_rear_right, pwm_rear_left):
    # TODO: Integrate this function with STSPIN948 pwm driver
    pass

# High-level API functions
def rover_move(throttle, dir_rot):
 
    # Map throttle and dir_rot to linear and angular velocities
    Vy = throttle  # Forward/backward speed
    omega = dir_rot  # Rotational speed

    # This would need to be updated, some scaling may be needed
    pwm_front_left = Vy + omega
    pwm_front_right = Vy - omega
    pwm_rear_left = Vy + omega
    pwm_rear_right = Vy - omega

    # Normalize PWM values to be within -100 to 100
    max_pwm = max(
        abs(pwm_front_left),
        abs(pwm_front_right),
        abs(pwm_rear_left),
        abs(pwm_rear_right)
    )
    if max_pwm > 100:
        scale = 100 / max_pwm
        pwm_front_left *= scale
        pwm_front_right *= scale
        pwm_rear_left *= scale
        pwm_rear_right *= scale

    rover_move_ll(pwm_front_left, pwm_front_right, pwm_rear_right, pwm_rear_left)

def rover_mechanum_move(throttle, dir_x, dir_y):
  
    # Calculate directional speeds
    Vx = (dir_x / 100) * throttle  # Lateral speed
    Vy = (dir_y / 100) * throttle  # Forward/backward speed
    omega = 0  # No rotation

    # Calculate PWM values for each wheel, mechanum wheel logic to be validated
    pwm_front_left = Vy + Vx + omega
    pwm_front_right = Vy - Vx - omega
    pwm_rear_left = Vy - Vx + omega
    pwm_rear_right = Vy + Vx - omega

    # Normalize PWM values to be within -100 to 100
    max_pwm = max(
        abs(pwm_front_left),
        abs(pwm_front_right),
        abs(pwm_rear_left),
        abs(pwm_rear_right)
    )
    if max_pwm > 100:
        scale = 100 / max_pwm
        pwm_front_left *= scale
        pwm_front_right *= scale
        pwm_rear_left *= scale
        pwm_rear_right *= scale

    # Send PWM values to the motors
    rover_move_ll(pwm_front_left, pwm_front_right, pwm_rear_right, pwm_rear_left)

def rover_rotate(target_angle):
  
    import time

    # Constants for the control loop
    ANGLE_TOLERANCE = 1.0  # Degrees
    KP = 0.5  # Proportional gain for the controller

    def get_current_angle():
        # TODO: read angle from the IMU
        return 0.0

    # Calculate initial error
    current_angle = get_current_angle()
    error = (target_angle - current_angle + 180) % 360 - 180

    # Control loop to rotate the rover, PI loop
    while abs(error) > ANGLE_TOLERANCE:
        # Calculate rotational speed with proportional control
        omega = KP * error

        # Limit omega to -100 to 100
        omega = max(min(omega, 100), -100)

        # No linear movement during rotation
        Vy = 0
        Vx = 0

        # Calculate PWM values for each wheel
        pwm_front_left = Vy + Vx + omega
        pwm_front_right = Vy - Vx - omega
        pwm_rear_left = Vy - Vx + omega
        pwm_rear_right = Vy + Vx - omega

        # Normalize PWM values to be within -100 to 100
        max_pwm = max(
            abs(pwm_front_left),
            abs(pwm_front_right),
            abs(pwm_rear_left),
            abs(pwm_rear_right)
        )
        if max_pwm > 100:
            scale = 100 / max_pwm
            pwm_front_left *= scale
            pwm_front_right *= scale
            pwm_rear_left *= scale
            pwm_rear_right *= scale

        # Send PWM values to the motors
        rover_move_ll(pwm_front_left, pwm_front_right, pwm_rear_right, pwm_rear_left)

        # Wait for a short period before the next iteration, adjust as needed
        time.sleep(0.1)

        # Update the current angle and error
        current_angle = get_current_angle()
        error = (target_angle - current_angle + 180) % 360 - 180

    # Stop the rover after reaching the target angle
    rover_move_ll(0, 0, 0, 0)
