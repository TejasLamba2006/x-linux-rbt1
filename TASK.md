I have an existing joystick-controlled robot interface built for the X-LINUX-RBT01
package/board. I need you to replace its motor control backend with a custom UART
protocol for our own hardware setup. Keep the existing joystick UI/frontend logic
if possible, and swap out only the motor command layer.

## Target system access

SSH into the board first: `ssh root@10.181.138.120`
This is a STM32MP257F-DK running embedded Linux. All development/testing should
happen on this machine directly (or deployed there).

## Hardware setup

- Main board: STM32MP257F-DK (Linux host, no direct motor control, just sends UART commands)
- 4 wheels, each driven by a separate STM32 Nucleo + STEVAL-IHM023V3 motor driver board
- Each motor board connects to the main board via its onboard ST-LINK USB Virtual COM Port
- Confirmed working ports so far: /dev/ttyACM0, /dev/ttyACM1, /dev/ttyACM2, /dev/ttyACM3 (need to
  identify/confirm a 4th port or check if one board handles 2 motors)
- Baud rate: 115200
- Confirmed mapping so far: /dev/ttyACM0 = Rear-Left (RL) wheel — please help me
  test and confirm the rest (ACM1, ACM2, and locate the 4th if it exists)

## Protocol details

Custom binary frame protocol, header AA 55, followed by board ID byte, command byte,
length byte, payload bytes, then 2 checksum bytes. Confirmed working commands:

- NOP:              AA 55 0A 00 00 51 C2
- SPEED_FWD (run):  AA 55 0A 01 03 80 00 00 3C DD
- SPEED_REV (run):  AA 55 0A 02 03 80 00 00 78 DD
- TORQUE_FWD (run): AA 55 0A 03 03 80 00 00 45 1D
- TORQUE_REV (run): AA 55 0A 04 03 80 00 00 F0 DD
- SET_MODE_SPEED:   AA 55 0A 05 00 52 92
- SET_MODE_TORQUE:  AA 55 0A 06 00 52 62
- START_MOTOR:      AA 55 0A 07 00 53 F2
- GET_STATUS:       AA 55 0A 08 00 56 02
- GET_SPEED:        AA 55 0A 09 00 57 92
- GET_TORQUE:       AA 55 0A 0A 00 57 62
- CLEAR_FAULTS:     AA 55 0A 0B 00 56 F2
- SET_ACCEL_ONLY:   AA 55 0A 0C 03 00 00 50 10 C8
- SET_TIME_ONLY:    AA 55 0A 0D 02 00 20 1E B5
- HEARTBEAT:        AA 55 0A 0E 00 55 A2
- SET_CURRENT_LIMIT:AA 55 0A 0F 02 88 13 39 18

Confirmed working startup sequence per motor board before it will actually spin:

1. CLEAR_FAULTS
2. SET_MODE_SPEED
3. START_MOTOR
4. Then send SPEED_FWD / SPEED_REV with desired speed payload

Additionally, per-wheel left/right turning frames exist (different protocol variant,
board-ID addressed 01/02/03/04 = FL/FR/RL/RR) for coordinated turning — I'll provide
these separately once basic per-wheel spin is fully validated on all 4 wheels.

## What I need you to build

1. A Python backend (pyserial-based) that:
   - Opens all 4 serial ports (confirm mapping first via a test/discovery script)
   - Implements a clean function library: connect(), send_frame(hex_or_bytes),
     read_response(), plus high-level helpers like set_speed(wheel, speed, direction),
     stop_all(), clear_faults(wheel), get_status(wheel)
   - Runs the required init sequence (CLEAR_FAULTS -> SET_MODE_SPEED -> START_MOTOR)
     automatically per wheel on startup
   - Includes a checksum/frame builder function so we don't have to hardcode every
     possible speed value as a separate hex string — needs to compute checksums
     dynamically for arbitrary speed/direction values
2. Replace the X-LINUX-RBT01 motor control calls in the existing joystick interface
   with calls into this new backend (map joystick X/Y axes to per-wheel forward/
   reverse/turn commands for a 4-wheel mecanum-style drive, since these are mecanum
   wheels — implement standard mecanum drive kinematics: strafe, rotate, forward/back)
3. Keep whatever existing joystick capture/UI layer already works (web-based,
   gamepad API, or whatever the current package uses) — just swap the motor command
   plumbing underneath
4. Add a safety STOP: on joystick release/neutral or app exit, immediately send
   SPEED_FWD/REV with zero speed payload (or equivalent stop) to all 4 wheels
5. Add basic logging/debug output showing which frame was sent to which wheel and
   what response came back, so we can debug in real time

## Important constraints

- Do not assume checksum algorithm — inspect the provided example frames above
  (multiple different payloads with different checksums) and reverse-engineer the
  exact checksum computation (likely CRC-8, XOR-sum, or simple additive checksum
  over header+id+cmd+len+payload) before building the dynamic frame builder.
  Validate your derived checksum function against ALL the example frames above —
  it must reproduce every listed checksum exactly.
- Test each change incrementally over SSH on the real hardware before assuming it works
- Confirm each wheel's port mapping explicitly before wiring up the mecanum kinematics,
  since sending the wrong command to the wrong port could cause unexpected motion
