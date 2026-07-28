#!/usr/bin/env python3
# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# BSD 3-Clause License. See uart_motors.py header.
"""
Port discovery / wheel-mapping tool.

Run on the board (SSH in first):

    python3 discover_ports.py            # enumerate + probe every /dev/ttyACMx
    python3 discover_ports.py --spin     # also briefly spin each wheel so you
                                         # can see WHICH physical wheel moves

It sends NOP + GET_STATUS to each port and prints the raw response, then
(optionally) runs the init sequence + a short forward spin on one port at a
time so you can watch which wheel turns and confirm the FL/FR/RL/RR mapping.

RL = /dev/ttyACM0 is already confirmed. Use this to confirm the rest.
"""

import argparse
import glob
import logging
import sys
import time

import uart_motors as um

logging.basicConfig(level=logging.DEBUG, format="%(message)s")
logger = logging.getLogger("discover")


def find_ports():
    """List all ST-LINK VCP ports present on the board."""
    ports = sorted(glob.glob("/dev/ttyACM*"))
    if not ports:
        logger.error("No /dev/ttyACM* ports found. Are the Nucleo boards plugged in?")
    return ports


def probe(port: str) -> None:
    """Open a port, send NOP + GET_STATUS, dump whatever comes back."""
    board = um.MotorBoard(port, name=port)
    if not board.connect(timeout=0.3):
        return
    logger.info("\n=== %s ===", port)
    board.send_command(um.CMD_NOP)
    time.sleep(0.05)
    board.send_command(um.CMD_GET_STATUS)
    resp = board.read_response(timeout=0.4)
    if resp:
        logger.info("%s GET_STATUS response: %s", port, resp.hex(" "))
    else:
        logger.info("%s no response bytes (board may not echo status)", port)
    board.close()


def spin(port: str, label: str) -> None:
    """Init + short forward spin on one port so you can identify the wheel."""
    board = um.MotorBoard(port, name=label)
    if not board.connect(timeout=0.2):
        return
    logger.info("\n>>> Spinning %s  (watch which physical wheel turns!) <<<", port)
    board.send_command(um.CMD_CLEAR_FAULTS)
    board.send_command(um.CMD_SET_MODE_SPEED)
    board.send_command(um.CMD_START_MOTOR)
    time.sleep(0.1)
    # gentle half-throttle forward spin for ~1.5s
    board.send_command(um.CMD_SPEED_FWD, um.speed_payload(0x80))
    time.sleep(1.5)
    board.send_command(um.CMD_SPEED_FWD, um.speed_payload(0))  # stop
    time.sleep(0.2)
    board.close()
    logger.info(">>> %s stopped. Which wheel moved? <<<", port)


def main():
    ap = argparse.ArgumentParser(description="Discover UART motor board ports")
    ap.add_argument("--spin", action="store_true",
                    help="briefly spin each wheel to identify its position")
    ap.add_argument("--ports", nargs="*",
                    help="explicit port list (default: all /dev/ttyACM*)")
    args = ap.parse_args()

    ports = args.ports or find_ports()
    if not ports:
        sys.exit(1)

    logger.info("Found %d port(s): %s", len(ports), ", ".join(ports))

    for p in ports:
        probe(p)

    if args.spin:
        logger.info("\n--- SPIN TEST: one wheel at a time, 3s between each ---")
        logger.info("Have someone watch the rover. Note which wheel moves.\n")
        for i, p in enumerate(ports):
            input(f"Press ENTER to spin {p} (wheel #{i})... ")
            spin(p, f"wheel#{i}")
            time.sleep(1)
        logger.info("\nDone. Map each port to FL/FR/RL/RR in uart_motors.DEFAULT_WHEELS.")


if __name__ == "__main__":
    main()
