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
        self.throttle: int = 0          # vy: forward(+)/backward(-), -100..100
        self.rotation: int = 0          # omega: in-place rotation dial, -100..100

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


# Motors physically stall below ~25% duty (buzz but don't turn), so treat that
# as a dead zone: any nonzero duty under MIN_DUTY is zeroed rather than sent as
# a signal the wheels can't act on. Applies to every input path (joystick,
# voice, vision) since all sides flow through _deadzone() before STSPIN.
MIN_DUTY = 25


def _deadzone(duty: int) -> int:
    """Zero out sub-stall duty; leave 0 and >=MIN_DUTY untouched."""
    return 0 if 0 < duty < MIN_DUTY else duty


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
    valid_modes = ['locked', 'controller', 'hybrid', 'follow-me', 'autopilot']
    
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
    Set the steering factor based on right joystick X-axis position and
    re-apply the combined drive.

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

        apply_drive()

    except Exception as e:
        logger.error(f"Error in direction(): {e}")
        state.reset_factors()


# =============================================================================
# THROTTLE / ROTATION CONTROL (COMBINED DRIVE)
# =============================================================================
def throttle_value(value: int) -> None:
    """
    Set forward/backward velocity (vy) and re-apply the combined drive.

    Args:
        value: Throttle value from -100 (full reverse) to 100 (full forward)
    """
    state.throttle = int(clamp(value, -100, 100))
    apply_drive()


def rotate_angle(angle: int) -> None:
    """
    Set in-place rotation speed (omega) and re-apply the combined drive.

    Args:
        angle: Rotation speed from -100 to 100
               Positive = rotate right, Negative = rotate left
    """
    state.rotation = int(clamp(angle, -100, 100))
    apply_drive()


def apply_drive() -> None:
    """
    Recompute and apply per-side wheel speeds from throttle, steering
    factors, and rotation combined.

    Steering factors (from direction()) only scale a side down when
    driving straight; rotation is added on top so the rover can rotate
    while stationary, while driving straight, or while steering.
    """
    if not validate_motor_driver():
        return

    try:
        value = state.throttle
        omega = state.rotation

        # Steering factors scale drive speed per side (0.0 - 1.0).
        left_drive = value * state.left_factor
        right_drive = value * state.right_factor

        # Rotation adds a spin component: right side backs off / reverses
        # for positive omega (rotate right), left side for negative omega.
        left_speed = left_drive + omega
        right_speed = right_drive - omega

        # Scale down (never up) so the combined value never exceeds
        # +/-100 duty while preserving the ratio between sides.
        side_max = max(abs(left_speed), abs(right_speed), 100)
        scale = 100.0 / side_max
        left_speed *= scale
        right_speed *= scale

        left_duty = _deadzone(int(clamp(abs(left_speed), 0, 100)))
        right_duty = _deadzone(int(clamp(abs(right_speed), 0, 100)))
        left_dir = 0 if left_speed >= 0 else 1
        right_dir = 0 if right_speed >= 0 else 1

        logger.debug(
            f"Drive: throttle={value} omega={omega} -> "
            f"L={left_duty}({left_dir}) R={right_duty}({right_dir})"
        )

        # Apply to left side motors (motor_1a, motor_2a)
        STSPIN.motor_1a(left_duty, left_dir)
        STSPIN.motor_2a(left_duty, left_dir)

        # Apply to right side motors (motor_1b, motor_2b)
        STSPIN.motor_1b(right_duty, right_dir)

        # Handle motor_2b (STM32MP157 has inverted PWM)
        if Board == "stm32mp257":
            STSPIN.motor_2b(right_duty, right_dir)
        else:
            # STM32MP157: inverted PWM
            STSPIN.motor_2b(100 - right_duty, right_dir)

    except Exception as e:
        logger.error(f"Error in apply_drive(): {e}")
        stop()


# =============================================================================
# COMMAND PARSER
# =============================================================================
def parser(parsed_data: Dict[str, Any]) -> None:
    """
    Parse incoming commands from the web interface.

    Each of dir_x, throttle and dir_rot independently updates one component
    of the combined drive state (steering factors, throttle, rotation) and
    immediately re-applies both wheel sides, so any combination of
    driving/steering/rotating works without needing another input held.

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
        
        # Only process motor commands in controller/hybrid mode. Differential
        # drive has no strafe hardware, so hybrid behaves identically to
        # controller here (dir_x is already steering, not strafe).
        if state.active_mode not in ('controller', 'hybrid'):
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
        state.throttle = 0
        state.rotation = 0

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
