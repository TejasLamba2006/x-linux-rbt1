#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

"""
Mecanum Wheel (Omnidirectional Drive) API

Motor Layout:
    motor_1a (Front Left)   ----   motor_1b (Front Right)
    motor_2a (Rear Left)    ----   motor_2b (Rear Right)

Control Pattern:
    - Left Joystick (throttle): forward(+)/backward(-) velocity      -> vy
    - Right Joystick X-axis (dir_x): right(+)/left(-) strafe velocity -> vx
    - Right Joystick dial (dir_rot): clockwise(+)/counter-clockwise(-) -> omega

vy, vx and omega are tracked independently and combined every time any one
of them changes, using the standard mecanum wheel-mixing equations. This
lets the rover strafe, drive, and rotate simultaneously - none of the three
inputs requires another to be held.

    FL (1a) = vy + vx + omega
    FR (1b) = vy - vx - omega
    RL (2a) = vy - vx + omega
    RR (2b) = vy + vx - omega
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


# =============================================================================
# BOARD DETECTION & MOTOR DRIVER IMPORT
# =============================================================================
def read_board_compatibility_name() -> str:
    """Read the board compatibility name from device tree."""
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
    """Holds the current combined drive inputs (throttle, strafe, rotation)."""

    def __init__(self):
        self.active_mode: str = 'locked'
        self.throttle: int = 0   # vy: forward(+)/backward(-), -100..100
        self.strafe: int = 0     # vx: right(+)/left(-), -100..100
        self.rotation: int = 0   # omega: CW(+)/CCW(-), -100..100

    def reset_inputs(self) -> None:
        """Reset all drive inputs to neutral (stopped)."""
        self.throttle = 0
        self.strafe = 0
        self.rotation = 0


state = MotorState()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max bounds."""
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
    """Select the operating mode ('locked', 'controller', 'follow-me', 'autopilot')."""
    valid_modes = ['locked', 'controller', 'follow-me', 'autopilot']

    if mode not in valid_modes:
        logger.warning(f"Invalid mode: {mode}. Valid modes: {valid_modes}")
        return

    state.active_mode = mode
    logger.info(f"Mode changed to: {mode}")

    if mode == 'locked':
        stop()


# =============================================================================
# DRIVE INPUTS (THROTTLE / STRAFE / ROTATION)
# =============================================================================
def throttle_value(value: int) -> None:
    """Set forward/backward velocity (vy) and re-apply combined drive."""
    state.throttle = int(clamp(value, -100, 100))
    apply_drive()


def direction(x_axis: int, y_axis: int) -> None:
    """
    Set strafe velocity (vx) from the right joystick's X-axis and re-apply
    combined drive.

    y_axis is not used for movement: forward/backward is controlled
    exclusively by the throttle (left) stick, so the right stick's vertical
    component would otherwise duplicate/conflict with throttle.
    """
    state.strafe = int(clamp(x_axis, -100, 100))
    apply_drive()


def rotate_angle(angle: int) -> None:
    """Set in-place rotation speed (omega) and re-apply combined drive."""
    state.rotation = int(clamp(angle, -100, 100))
    apply_drive()


# =============================================================================
# WHEEL MIXING
# =============================================================================
def _drive_wheel(motor_fn, value: float) -> None:
    """Convert a signed wheel-speed value to a duty/direction call."""
    duty = int(clamp(abs(value), 0, 100))
    direction_flag = 0 if value >= 0 else 1
    motor_fn(duty, direction_flag)


def _drive_wheel_2b(value: float) -> None:
    """motor_2b needs inverted PWM duty on STM32MP157."""
    duty = int(clamp(abs(value), 0, 100))
    direction_flag = 0 if value >= 0 else 1
    if Board == "stm32mp257":
        STSPIN.motor_2b(duty, direction_flag)
    else:
        STSPIN.motor_2b(100 - duty, direction_flag)


def apply_drive() -> None:
    """Recompute and apply all 4 wheel speeds from the current combined state."""
    if not validate_motor_driver():
        return

    try:
        vy = state.throttle
        vx = state.strafe
        omega = state.rotation

        fl = vy + vx + omega
        fr = vy - vx - omega
        rl = vy - vx + omega
        rr = vy + vx - omega

        # Scale down (never up) so combined inputs never exceed +/-100 duty
        # while preserving the ratio between wheels.
        wheel_max = max(abs(fl), abs(fr), abs(rl), abs(rr), 100)
        scale = 100.0 / wheel_max
        fl *= scale
        fr *= scale
        rl *= scale
        rr *= scale

        _drive_wheel(STSPIN.motor_1a, fl)
        _drive_wheel(STSPIN.motor_1b, fr)
        _drive_wheel(STSPIN.motor_2a, rl)
        _drive_wheel_2b(rr)

        logger.debug(
            f"Drive: vy={vy} vx={vx} omega={omega} -> "
            f"FL={fl:.0f} FR={fr:.0f} RL={rl:.0f} RR={rr:.0f}"
        )

    except Exception as e:
        logger.error(f"Error in apply_drive(): {e}")
        stop()


# =============================================================================
# COMMAND PARSER
# =============================================================================
def parser(parsed_data: Dict[str, Any]) -> None:
    """
    Parse incoming commands from the web interface.

    Each of throttle, dir_x and dir_rot independently updates one component
    of the combined drive state and immediately re-applies all 4 wheel
    speeds, so any combination of driving/strafing/rotating works without
    needing another input to be held.
    """
    if not isinstance(parsed_data, dict):
        logger.warning(f"Invalid command format: {type(parsed_data)}")
        return

    try:
        if "mode" in parsed_data:
            mode_select(parsed_data['mode'])

        if state.active_mode != 'controller':
            return

        if "throttle" in parsed_data:
            throttle_value(parsed_data['throttle'])

        if "dir_x" in parsed_data:
            direction(parsed_data.get('dir_x', 0), parsed_data.get('dir_y', 0))

        if "dir_rot" in parsed_data:
            rotate_angle(parsed_data['dir_rot'])

    except Exception as e:
        logger.error(f"Error parsing command: {e}")


# =============================================================================
# STOP & RELEASE
# =============================================================================
def stop() -> None:
    """Stop all motors immediately and reset all drive inputs."""
    if not validate_motor_driver():
        return

    try:
        state.reset_inputs()

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
