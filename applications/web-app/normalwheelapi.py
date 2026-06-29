#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

"""
Normal Wheel (Differential Drive) API

This module provides motor control for 4-wheel vehicles with standard wheels
using differential drive kinematics.

Motor Layout:
    motor_1a (Front Left)   ----   motor_1b (Front Right)
    motor_2a (Rear Left)    ----   motor_2b (Rear Right)

Control Pattern:
    - Left Joystick: Controls SPEED (throttle) - forward/backward
    - Right Joystick X-axis: Controls STEERING FACTOR - adjusts wheel speeds
        - Move right = slow down right wheels (turn right)
        - Move left = slow down left wheels (turn left)
    - Speed is ONLY applied when throttle is used
"""

import logging
from typing import Dict, Any, Optional

# Setup module logger
logger = logging.getLogger(__name__)

# =============================================================================
# BOARD DETECTION & MOTOR DRIVER IMPORT
# =============================================================================
def read_board_compatibility_name() -> str:
    """
    Read the board compatibility name from device tree.
    
    Returns:
        Board name string (e.g., 'stm32mp257', 'stm32mp157')
    """
    try:
        with open("/proc/device-tree/compatible") as fp:
            content = fp.read()
            return content.split(',')[-1].rstrip('\x00')
    except FileNotFoundError:
        logger.warning("Device tree not found, defaulting to 'all'")
        return "all"
    except Exception as e:
        logger.error(f"Error reading board compatibility: {e}")
        return "all"


# Detect board and import appropriate motor driver
Board = read_board_compatibility_name()
STSPIN = None

try:
    if Board == "stm32mp257":
        import stm32mp2 as STSPIN
        logger.info(f"Loaded motor driver for {Board}")
    elif Board == "stm32mp157":
        import stm32mp1 as STSPIN
        logger.info(f"Loaded motor driver for {Board}")
    else:
        logger.warning(f"Unknown board: {Board}, attempting stm32mp1 driver")
        import stm32mp1 as STSPIN
except ImportError as e:
    logger.error(f"Failed to import motor driver: {e}")
    raise


# =============================================================================
# GLOBAL STATE
# =============================================================================
class MotorState:
    """Encapsulates the motor control state."""
    
    def __init__(self):
        self.active_mode: str = 'locked'
        self.left_factor: float = 1.0   # Left side motor factor (0.0 to 1.0)
        self.right_factor: float = 1.0  # Right side motor factor (0.0 to 1.0)
        self.last_throttle: int = 0     # Last throttle value for reference
    
    def reset_factors(self) -> None:
        """Reset steering factors to default (straight)."""
        self.left_factor = 1.0
        self.right_factor = 1.0


# Global state instance
state = MotorState()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp a value between min and max bounds.
    
    Args:
        value: The value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        
    Returns:
        The clamped value
    """
    return max(min_val, min(max_val, value))


def validate_motor_driver() -> bool:
    """Check if motor driver is available."""
    if STSPIN is None:
        logger.error("Motor driver not initialized")
        return False
    return True


# =============================================================================
# MODE CONTROL
# =============================================================================
def mode_select(mode: str) -> None:
    """
    Select the operating mode.
    
    Args:
        mode: Operating mode ('locked', 'controller', 'follow-me', 'autopilot')
    """
    valid_modes = ['locked', 'controller', 'follow-me', 'autopilot']
    
    if mode not in valid_modes:
        logger.warning(f"Invalid mode: {mode}. Valid modes: {valid_modes}")
        return
    
    state.active_mode = mode
    logger.info(f"Mode changed to: {mode}")
    
    # Stop motors when switching to locked mode
    if mode == 'locked':
        stop()


# =============================================================================
# DIRECTION CONTROL (STEERING FACTORS)
# =============================================================================
def direction(x_axis: int, y_axis: int) -> None:
    """
    Set the steering factor based on right joystick position.
    
    This does NOT move the robot - it only sets the steering factor
    that will be applied when throttle is used.
    
    Args:
        x_axis: Steering value (-100 to 100)
                Positive (right) = slow down right wheels
                Negative (left) = slow down left wheels
        y_axis: Ignored for differential drive (no lateral movement)
    """
    try:
        # Validate input
        x_axis = int(clamp(x_axis, -100, 100))
        
        # Normalize x_axis to -1.0 to 1.0
        steering = x_axis / 100.0
        
        # Calculate wheel factors based on steering
        if steering >= 0:
            # Turning right: reduce right wheel speed
            state.left_factor = 1.0
            state.right_factor = 1.0 - steering
        else:
            # Turning left: reduce left wheel speed
            state.left_factor = 1.0 + steering
            state.right_factor = 1.0
        
        # Ensure factors are in valid range
        state.left_factor = clamp(state.left_factor, 0.0, 1.0)
        state.right_factor = clamp(state.right_factor, 0.0, 1.0)
        
        logger.debug(f"Steering: L={state.left_factor:.2f}, R={state.right_factor:.2f}")
        
        # Reset factors if joystick is centered
        if x_axis == 0 and y_axis == 0:
            state.reset_factors()
            
    except Exception as e:
        logger.error(f"Error in direction(): {e}")
        state.reset_factors()


# =============================================================================
# THROTTLE CONTROL
# =============================================================================
def throttle_value(value: int) -> None:
    """
    Apply throttle with current steering factors.
    
    This is the main function that actually moves the robot.
    Speed is determined by throttle value, direction by steering factors.
    
    Args:
        value: Throttle value from -100 (full reverse) to 100 (full forward)
    """
    if not validate_motor_driver():
        return
    
    try:
        # Validate and clamp input
        value = int(clamp(value, -100, 100))
        state.last_throttle = value
        
        # Calculate actual motor speeds
        left_speed = int(abs(value) * state.left_factor)
        right_speed = int(abs(value) * state.right_factor)
        
        # Determine direction (0 = forward, 1 = reverse)
        direction_flag = 0 if value >= 0 else 1
        
        logger.debug(f"Throttle: {value}, L={left_speed}, R={right_speed}, dir={direction_flag}")
        
        # Apply to left side motors (motor_1a, motor_2a)
        STSPIN.motor_1a(left_speed, direction_flag)
        STSPIN.motor_2a(left_speed, direction_flag)
        
        # Apply to right side motors (motor_1b, motor_2b)
        STSPIN.motor_1b(right_speed, direction_flag)
        
        # Handle motor_2b (STM32MP157 has inverted PWM)
        if Board == "stm32mp257":
            STSPIN.motor_2b(right_speed, direction_flag)
        else:
            # STM32MP157: inverted PWM
            STSPIN.motor_2b(100 - right_speed, direction_flag)
            
    except Exception as e:
        logger.error(f"Error in throttle_value(): {e}")
        stop()


# =============================================================================
# ROTATION CONTROL
# =============================================================================
def rotate_angle(angle: int) -> None:
    """
    Rotate the robot in place using rotation dial.
    
    This bypasses the steering factors and directly controls rotation.
    
    Args:
        angle: Rotation speed from -100 to 100
               Positive = rotate right, Negative = rotate left
    """
    if not validate_motor_driver():
        return
    
    try:
        angle = int(clamp(angle, -100, 100))
        
        if angle >= 0:
            rotate_right(abs(angle))
        else:
            rotate_left(abs(angle))
            
    except Exception as e:
        logger.error(f"Error in rotate_angle(): {e}")
        stop()


def rotate_right(speed: int) -> None:
    """
    Rotate right in place (clockwise when viewed from above).
    
    Args:
        speed: Rotation speed (0 to 100)
    """
    if not validate_motor_driver():
        return
    
    speed = int(clamp(speed, 0, 100))
    
    try:
        # Left side forward
        STSPIN.motor_1a(speed, 0)
        STSPIN.motor_2a(speed, 0)
        
        # Right side backward
        STSPIN.motor_1b(speed, 1)
        if Board == "stm32mp257":
            STSPIN.motor_2b(speed, 1)
        else:
            STSPIN.motor_2b(100 - speed, 1)
            
    except Exception as e:
        logger.error(f"Error in rotate_right(): {e}")


def rotate_left(speed: int) -> None:
    """
    Rotate left in place (counter-clockwise when viewed from above).
    
    Args:
        speed: Rotation speed (0 to 100)
    """
    if not validate_motor_driver():
        return
    
    speed = int(clamp(speed, 0, 100))
    
    try:
        # Left side backward
        STSPIN.motor_1a(speed, 1)
        STSPIN.motor_2a(speed, 1)
        
        # Right side forward
        STSPIN.motor_1b(speed, 0)
        if Board == "stm32mp257":
            STSPIN.motor_2b(speed, 0)
        else:
            STSPIN.motor_2b(100 - speed, 0)
            
    except Exception as e:
        logger.error(f"Error in rotate_left(): {e}")


# =============================================================================
# COMMAND PARSER
# =============================================================================
def parser(parsed_data: Dict[str, Any]) -> None:
    """
    Parse incoming commands from the web interface.
    
    Control flow:
        1. direction() sets steering factors (right joystick)
        2. throttle_value() applies speed with those factors (left joystick)
        3. rotate_angle() for in-place rotation (rotation dial)
    
    Args:
        parsed_data: Dictionary containing command data
            - mode: Operating mode
            - throttle: Forward/backward speed
            - dir_x, dir_y: Steering input
            - dir_rot: Rotation angle
    """
    if not isinstance(parsed_data, dict):
        logger.warning(f"Invalid command format: {type(parsed_data)}")
        return
    
    try:
        # Handle mode change
        if "mode" in parsed_data:
            mode_select(parsed_data['mode'])
        
        # Only process motor commands in controller mode
        if state.active_mode != 'controller':
            return
        
        # Process direction (sets steering factors)
        if "dir_x" in parsed_data:
            dir_x = parsed_data.get('dir_x', 0)
            dir_y = parsed_data.get('dir_y', 0)
            direction(dir_x, dir_y)
        
        # Process throttle (applies speed with factors)
        if "throttle" in parsed_data:
            throttle_value(parsed_data['throttle'])
        
        # Process rotation dial
        if "dir_rot" in parsed_data:
            rotate_angle(parsed_data['dir_rot'])
        
        # If direction changed but no throttle in this message, re-apply last throttle
        if "dir_x" in parsed_data and "throttle" not in parsed_data and state.last_throttle != 0:
            throttle_value(state.last_throttle)
            
    except Exception as e:
        logger.error(f"Error parsing command: {e}")


# =============================================================================
# STOP & RELEASE
# =============================================================================
def stop() -> None:
    """Stop all motors immediately."""
    if not validate_motor_driver():
        return
    
    try:
        state.reset_factors()
        state.last_throttle = 0
        
        STSPIN.motor_1a(0, 0)
        STSPIN.motor_1b(0, 0)
        STSPIN.motor_2a(0, 0)
        
        if Board == "stm32mp257":
            STSPIN.motor_2b(0, 0)
        else:
            STSPIN.motor_2b(100, 0)  # Inverted PWM
        
        logger.info("Motors stopped")
        
    except Exception as e:
        logger.error(f"Error stopping motors: {e}")


def release() -> None:
    """Release motor driver resources."""
    try:
        stop()
        if STSPIN:
            STSPIN.release()
        logger.info("Motor driver released")
    except Exception as e:
        logger.error(f"Error releasing motor driver: {e}")
