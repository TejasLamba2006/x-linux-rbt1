#!/usr/bin/env python3
# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause
"""
Custom UART Motor Backend for the STM32MP257F-DK rover.

Replaces the STSPIN GPIO/PWM driver with a pyserial backend that talks to
four independent STM32 Nucleo + STEVAL-IHM023V3 motor boards, each reached
through its ST-LINK USB Virtual COM Port (/dev/ttyACMx).

Frame format (all multi-byte integers little-endian on the wire):

    AA 55 <board_id> <cmd> <len> [payload ...] <crc_lo> <crc_hi>

    - header    : AA 55
    - board_id  : 0x0A (the confirmed per-wheel board address)
    - cmd       : command opcode
    - len       : number of payload bytes
    - payload   : `len` bytes
    - crc       : CRC-16/MODBUS over board_id + cmd + len + payload,
                  transmitted low byte first.

The CRC was reverse-engineered from the confirmed example frames and
reproduces every one of them exactly (see checksum_crack.py / verify).

This module exposes the SAME call surface the existing mecanum API expects
from the old `stm32mp2` driver -- motor_1a/1b/2a/2b(duty, dir), stop(),
release() -- so the joystick UI and mecanum kinematics are untouched.
"""

import logging
import threading
import time

try:
    import serial
except ImportError:  # pragma: no cover - pyserial missing at import time
    serial = None

logger = logging.getLogger(__name__)

# =============================================================================
# PROTOCOL CONSTANTS
# =============================================================================
HEADER = bytes([0xAA, 0x55])
BOARD_ID = 0x0A  # confirmed board address in every example frame

# Command opcodes
CMD_NOP              = 0x00
CMD_SPEED_FWD        = 0x01
CMD_SPEED_REV        = 0x02
CMD_TORQUE_FWD       = 0x03
CMD_TORQUE_REV       = 0x04
CMD_SET_MODE_SPEED   = 0x05
CMD_SET_MODE_TORQUE  = 0x06
CMD_START_MOTOR      = 0x07
CMD_GET_STATUS       = 0x08
CMD_GET_SPEED        = 0x09
CMD_GET_TORQUE       = 0x0A
CMD_CLEAR_FAULTS     = 0x0B
CMD_SET_ACCEL_ONLY   = 0x0C
CMD_SET_TIME_ONLY    = 0x0D
CMD_HEARTBEAT        = 0x0E
CMD_SET_CURRENT_LIMIT = 0x0F

CMD_NAMES = {
    CMD_NOP: "NOP", CMD_SPEED_FWD: "SPEED_FWD", CMD_SPEED_REV: "SPEED_REV",
    CMD_TORQUE_FWD: "TORQUE_FWD", CMD_TORQUE_REV: "TORQUE_REV",
    CMD_SET_MODE_SPEED: "SET_MODE_SPEED", CMD_SET_MODE_TORQUE: "SET_MODE_TORQUE",
    CMD_START_MOTOR: "START_MOTOR", CMD_GET_STATUS: "GET_STATUS",
    CMD_GET_SPEED: "GET_SPEED", CMD_GET_TORQUE: "GET_TORQUE",
    CMD_CLEAR_FAULTS: "CLEAR_FAULTS", CMD_SET_ACCEL_ONLY: "SET_ACCEL_ONLY",
    CMD_SET_TIME_ONLY: "SET_TIME_ONLY", CMD_HEARTBEAT: "HEARTBEAT",
    CMD_SET_CURRENT_LIMIT: "SET_CURRENT_LIMIT",
}

BAUD_RATE = 115200

# Maps the 0-100 "duty" the mecanum layer produces onto the 16-bit speed
# field the firmware expects. The confirmed run frame used 0x80 (128) for a
# half-throttle spin, so duty*10 -> 50% maps to 500 and 100% maps to 1000,
# keeping us inside the known-good range. Tune SPEED_SCALE if the wheels
# need more/less headroom.
SPEED_SCALE = 10
SPEED_MAX = 0xFFFF


# =============================================================================
# CRC-16/MODBUS  (poly 0xA001 reflected, init 0xFFFF, no final xor)
# =============================================================================
def crc16_modbus(data: bytes) -> int:
    """Return the CRC-16/MODBUS of `data` as a 16-bit int."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def build_frame(cmd: int, payload: bytes = b"", board_id: int = BOARD_ID) -> bytes:
    """
    Build a complete wire frame for `cmd` with the given payload.

    The checksum is computed dynamically, so arbitrary speed/direction values
    work without hardcoding hex strings.
    """
    payload = bytes(payload)
    body = bytes([board_id, cmd, len(payload)]) + payload
    crc = crc16_modbus(body)
    return HEADER + body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def speed_payload(value: int) -> bytes:
    """
    Encode a speed magnitude into the 3-byte SPEED_FWD/REV payload.

    The confirmed run frame used payload 80 00 00 -- the speed lives in the
    FIRST byte (little-endian 16-bit value, low byte first, third byte 0x00).
    So 0x80 (128) -> [0x80, 0x00, 0x00], and 500 (0x01F4) -> [0xF4, 0x01, 0x00].
    """
    value = max(0, min(SPEED_MAX, int(value)))
    return bytes([value & 0xFF, (value >> 8) & 0xFF, 0x00])


# =============================================================================
# PER-BOARD SERIAL LINK
# =============================================================================
class MotorBoard:
    """One STM32 motor board behind one /dev/ttyACMx port."""

    def __init__(self, port: str, name: str, board_id: int = BOARD_ID):
        self.port = port
        self.name = name
        self.board_id = board_id
        self.ser = None
        self._lock = threading.Lock()

    def connect(self, timeout: float = 0.1) -> bool:
        """Open the serial port. Returns True on success."""
        if serial is None:
            logger.error("pyserial not installed -- cannot open %s", self.port)
            return False
        try:
            self.ser = serial.Serial(
                port=self.port, baudrate=BAUD_RATE, timeout=timeout,
                write_timeout=timeout,
            )
            # flush any boot garbage from the ST-LINK VCP
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            logger.info("[%s] opened %s @ %d", self.name, self.port, BAUD_RATE)
            return True
        except Exception as e:
            logger.error("[%s] failed to open %s: %s", self.name, self.port, e)
            self.ser = None
            return False

    def send_frame(self, frame: bytes) -> None:
        """Write a raw frame to the board (thread-safe)."""
        if self.ser is None:
            return
        with self._lock:
            try:
                self.ser.write(frame)
                self.ser.flush()
            except Exception as e:
                logger.error("[%s] write error: %s", self.name, e)

    def send_command(self, cmd: int, payload: bytes = b"", log: bool = True) -> None:
        """Build + send one command, with a debug trace of the exact bytes."""
        frame = build_frame(cmd, payload, self.board_id)
        if log:
            logger.debug("[%s] TX %-16s %s",
                         self.name, CMD_NAMES.get(cmd, f"0x{cmd:02X}"),
                         frame.hex(" "))
        self.send_frame(frame)

    def read_response(self, timeout: float = 0.2) -> bytes:
        """
        Best-effort read of one response frame. Returns the raw bytes or b''.

        Non-blocking-ish: bounded by `timeout` so it never stalls the control
        loop. Used for diagnostics (GET_STATUS/GET_SPEED), not for motion.
        """
        if self.ser is None:
            return b""
        end = time.monotonic() + timeout
        buf = bytearray()
        try:
            while time.monotonic() < end:
                chunk = self.ser.read(self.ser.in_waiting or 1)
                if chunk:
                    buf.extend(chunk)
                    # return once we plausibly have a full frame (>=7 bytes and
                    # a header somewhere); caller validates length/checksum
                    if len(buf) >= 7 and bytes(buf[:2]) == HEADER:
                        ln = buf[4] if len(buf) > 4 else 0
                        if len(buf) >= 5 + ln + 2:
                            break
        except Exception as e:
            logger.error("[%s] read error: %s", self.name, e)
        if buf:
            logger.debug("[%s] RX %s", self.name, bytes(buf).hex(" "))
        return bytes(buf)

    def close(self) -> None:
        with self._lock:
            if self.ser is not None:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None


# =============================================================================
# 4-WHEEL CONTROLLER
# =============================================================================
# Wheel positions -> (port, board_id). Mapping confirmed by the per-wheel
# spin test (discover_ports.py --spin): ACM0=RL, ACM1=FL, ACM2=RR, ACM3=FR.
DEFAULT_WHEELS = {
    "FL": ("/dev/ttyACM1", BOARD_ID),
    "FR": ("/dev/ttyACM3", BOARD_ID),
    "RL": ("/dev/ttyACM0", BOARD_ID),
    "RR": ("/dev/ttyACM2", BOARD_ID),
}


class UARTMotors:
    """
    Drop-in replacement for the old `stm32mp2` driver module.

    Exposes motor_1a/1b/2a/2b(duty, dir), stop(), release() so mechanumapi.py
    works unchanged, plus higher-level helpers (set_speed, clear_faults,
    get_status, init sequence).
    """

    # mecanum motor slot -> wheel name
    _SLOT_TO_WHEEL = {"1a": "FL", "1b": "FR", "2a": "RL", "2b": "RR"}

    def __init__(self, wheel_map: dict = None):
        self.wheel_map = wheel_map or DEFAULT_WHEELS
        self.boards = {
            name: MotorBoard(port, name, bid)
            for name, (port, bid) in self.wheel_map.items()
        }
        self._ready = set()  # wheels that finished the init sequence

    # ---- lifecycle --------------------------------------------------------
    def connect(self) -> dict:
        """Open every port. Returns {wheel: ok} so callers can see what's up."""
        result = {}
        for name, board in self.boards.items():
            result[name] = board.connect()
        return result

    def init_wheel(self, wheel: str) -> bool:
        """
        Run the required startup sequence on one wheel:
        CLEAR_FAULTS -> SET_MODE_SPEED -> START_MOTOR.
        """
        board = self.boards.get(wheel)
        if board is None or board.ser is None:
            logger.warning("init_wheel(%s): not connected", wheel)
            return False
        board.send_command(CMD_CLEAR_FAULTS)
        board.send_command(CMD_SET_MODE_SPEED)
        board.send_command(CMD_START_MOTOR)
        self._ready.add(wheel)
        logger.info("[%s] init sequence done (CLEAR_FAULTS->SET_MODE_SPEED->START_MOTOR)", wheel)
        return True

    def init_all(self) -> None:
        for wheel in self.boards:
            if self.boards[wheel].ser is not None:
                self.init_wheel(wheel)

    def release(self) -> None:
        """Stop everything and close all ports."""
        try:
            self.stop()
        except Exception as e:
            logger.error("release stop error: %s", e)
        for board in self.boards.values():
            board.close()
        self._ready.clear()
        logger.info("All motor ports closed")

    # ---- motion -----------------------------------------------------------
    def set_speed(self, wheel: str, speed: int, direction: int) -> None:
        """
        Drive one wheel. `speed` is a 0-100 magnitude, `direction` is
        0=forward / 1=reverse. speed==0 sends a zero-throttle stop frame.
        """
        board = self.boards.get(wheel)
        if board is None or board.ser is None:
            return
        if wheel not in self._ready:
            self.init_wheel(wheel)

        magnitude = int(max(0, min(100, speed))) * SPEED_SCALE
        if magnitude == 0:
            # zero-throttle frame on the forward opcode == stop
            board.send_command(CMD_SPEED_FWD, speed_payload(0))
            return
        cmd = CMD_SPEED_REV if direction else CMD_SPEED_FWD
        board.send_command(cmd, speed_payload(magnitude))

    def stop_all(self) -> None:
        """Immediately zero every wheel (safety stop)."""
        for wheel in self.boards:
            self.set_speed(wheel, 0, 0)
        logger.info("STOP_ALL: zero-speed sent to all wheels")

    # ---- diagnostics ------------------------------------------------------
    def clear_faults(self, wheel: str) -> None:
        board = self.boards.get(wheel)
        if board and board.ser:
            board.send_command(CMD_CLEAR_FAULTS)

    def get_status(self, wheel: str) -> bytes:
        board = self.boards.get(wheel)
        if not board or not board.ser:
            return b""
        board.send_command(CMD_GET_STATUS)
        return board.read_response()

    def heartbeat(self, wheel: str = None) -> None:
        targets = [wheel] if wheel else list(self.boards)
        for w in targets:
            board = self.boards.get(w)
            if board and board.ser:
                board.send_command(CMD_HEARTBEAT)

    # ---- legacy driver shim (motor_1a/1b/2a/2b) ---------------------------
    def _slot(self, slot: str, duty: int, direction: int) -> None:
        wheel = self._SLOT_TO_WHEEL[slot]
        self.set_speed(wheel, duty, direction)

    def motor_1a(self, duty=50, dir=0):  # Front Left
        self._slot("1a", duty, dir)

    def motor_1b(self, duty=50, dir=0):  # Front Right
        self._slot("1b", duty, dir)

    def motor_2a(self, duty=50, dir=0):  # Rear Left
        self._slot("2a", duty, dir)

    def motor_2b(self, duty=50, dir=0):  # Rear Right
        self._slot("2b", duty, dir)

    def stop(self):
        self.stop_all()


# =============================================================================
# MODULE-LEVEL SINGLETON (matches `import stm32mp2 as STSPIN` usage)
# =============================================================================
_instance = None


def get_controller() -> UARTMotors:
    """Return the process-wide controller, connecting + initializing on first use."""
    global _instance
    if _instance is None:
        _instance = UARTMotors()
        _instance.connect()
        _instance.init_all()
    return _instance


def __getattr__(name):
    """
    Module-level proxy so `import uart_motors as STSPIN; STSPIN.motor_1a(...)`
    works exactly like the old driver module, lazily creating the controller.
    """
    ctrl = get_controller()
    if hasattr(ctrl, name):
        return getattr(ctrl, name)
    raise AttributeError(f"module 'uart_motors' has no attribute {name!r}")


# =============================================================================
# SELF-CHECK (run on host, no hardware needed)
# =============================================================================
def _self_check():
    """Verify build_frame reproduces every confirmed example frame."""
    cases = [
        ("NOP",               CMD_NOP,              b"",                 "AA550A000051C2"),
        ("SPEED_FWD",         CMD_SPEED_FWD,        bytes([0x80, 0, 0]), "AA550A01038000003CDD"),
        ("SPEED_REV",         CMD_SPEED_REV,        bytes([0x80, 0, 0]), "AA550A020380000078DD"),
        ("TORQUE_FWD",        CMD_TORQUE_FWD,       bytes([0x80, 0, 0]), "AA550A030380000045 1D".replace(" ", "")),
        ("TORQUE_REV",        CMD_TORQUE_REV,       bytes([0x80, 0, 0]), "AA550A0403800000F0DD"),
        ("SET_MODE_SPEED",    CMD_SET_MODE_SPEED,   b"",                 "AA550A05005292"),
        ("SET_MODE_TORQUE",   CMD_SET_MODE_TORQUE,  b"",                 "AA550A06005262"),
        ("START_MOTOR",       CMD_START_MOTOR,      b"",                 "AA550A070053F2"),
        ("GET_STATUS",        CMD_GET_STATUS,       b"",                 "AA550A08005602"),
        ("GET_SPEED",         CMD_GET_SPEED,        b"",                 "AA550A09005792"),
        ("GET_TORQUE",        CMD_GET_TORQUE,       b"",                 "AA550A0A005762"),
        ("CLEAR_FAULTS",      CMD_CLEAR_FAULTS,     b"",                 "AA550A0B0056F2"),
        ("SET_ACCEL_ONLY",    CMD_SET_ACCEL_ONLY,   bytes([0, 0, 0x50]), "AA550A0C0300005010C8"),
        ("SET_TIME_ONLY",     CMD_SET_TIME_ONLY,    bytes([0, 0x20]),    "AA550A0D0200201EB5"),
        ("HEARTBEAT",         CMD_HEARTBEAT,        b"",                 "AA550A0E0055A2"),
        ("SET_CURRENT_LIMIT", CMD_SET_CURRENT_LIMIT, bytes([0x88, 0x13]), "AA550A0F0288133918"),
    ]
    ok = True
    for name, cmd, payload, expected in cases:
        got = build_frame(cmd, payload).hex().upper()
        exp = expected.upper()
        status = "OK " if got == exp else "FAIL"
        if got != exp:
            ok = False
        print(f"{status} {name:18s} got={got} exp={exp}")
    print("\nALL FRAMES MATCH" if ok else "\nMISMATCH DETECTED")
    return ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    _self_check()
