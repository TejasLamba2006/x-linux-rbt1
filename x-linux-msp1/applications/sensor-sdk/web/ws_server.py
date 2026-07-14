#!/usr/bin/python3

##
##############################################################################
# @file   ws_server.py
# @author SRA-SAIL, Noida
# @brief  This script acts as the web socket server and
#     delivers real-time data to the sensor visualization webpage
##############################################################################
# @attention
#
# Copyright (c) 2024 STMicroelectronics.
# All rights reserved.
#
# This software is licensed under terms that can be found in the LICENSE file
# in the root directory of this software component.
# If no LICENSE file comes with this software, it is provided AS-IS.
#
##############################################################################
##

import websockets
import asyncio
import json
import math
from subprocess import Popen, PIPE, CalledProcessError

import sensor_config as config
import utils


port = config.WS_PORT
ip_address = utils.get_ipaddress()

pitch = 0.0
roll = 0.0
yaw = 0.0

if config.data_source == config.SensorDataSource.simulate:
    pitch_increment = math.pi / 40
    roll_increment = math.pi / 60
    yaw_increment = math.pi / 80
if config.data_source == config.SensorDataSource.static_file:
    import sensor_reader
if config.data_source == config.SensorDataSource.sense_hat:
    from sense_hat import SenseHat
if config.data_source == config.SensorDataSource.MSP01:
    import sensor_reader

# Sensor data units in radian


async def send_sensor_data_euler(websocket, pitch, roll, yaw):
    json_data = [{"type": "orientation", "Pitch": pitch, "Roll": roll, "Yaw": yaw}]
    try:
        await websocket.send(json.dumps(json_data))
    except websockets.exceptions.ConnectionClosed:
        return False
    print(
        "Pitch = {0}, Roll = {1}, Yaw = {2}".format(
            round(p, 3), round(r, 3), round(y, 3)
        )
    )
    return True


async def send_sensor_data_quaternion(websocket, x, y, z, w):
    # Axis mapping for STM32MP135F-DK
    json_data = [{"type": "quaternion", "x": -z, "y": -x, "z": -y, "w": w}]
    # json_data = [{"type": "quaternion", "x":z, "y":x, "z":y, "w":w}]
    try:
        await websocket.send(json.dumps(json_data))
    except websockets.exceptions.ConnectionClosed:
        return False
    return True


async def handle_connection(websocket, path):
    if websocket.remote_address:
        (host, port) = websocket.remote_address
        print(f"Client ({host}:{port}) Connected.. ")
    global pitch, roll, yaw

    run = True

    if config.data_source == config.SensorDataSource.simulate:
        while run:
            pitch = pitch + pitch_increment
            roll = roll + roll_increment
            yaw = yaw + yaw_increment

            run = send_sensor_data_euler(websocket, pitch, roll, yaw)
            # time.sleep(.05)
            await asyncio.sleep(0.5)

    if config.data_source == config.SensorDataSource.static_file:
        while run:
            euler = sensor_reader.euler_from_file()
            if not euler:
                break
            pitch = euler["pitch"]
            roll = euler["roll"]
            yaw = euler["yaw"]

            run = send_sensor_data_euler(websocket, pitch, roll, yaw)
            # time.sleep(.05)
            await asyncio.sleep(0.5)

    if config.data_source == config.SensorDataSource.sense_hat:
        while run:
            euler = sense.get_orientation_radians()
            if not euler:
                break

            run = send_sensor_data_euler(websocket, pitch, roll, yaw)
            # time.sleep(.05)
            await asyncio.sleep(0.5)

    if config.data_source == config.SensorDataSource.MSP01:
        with Popen(
            [
                "stdbuf",
                "-oL",
                "./iio_test_sensors",
                "-x",
                "20",
                "-a",
                "-c",
                "-1",
                "-o",
                "100",
                "-g",
                "0",
                "-w",
                "50",
                "ism330dhcx_accel",
                "ism330dhcx_gyro",
                "lsm303ah_magn",
            ],
            stdout=PIPE,
            stderr=PIPE,
            bufsize=1,
            universal_newlines=True,
        ) as gen_buffer:
            for line in gen_buffer.stdout:
                quaternion = sensor_reader.quaternion_from_gbuf_line(line)
                if not quaternion:
                    print("Value is not quaternion value")
                    continue
                x = quaternion["x"]
                y = quaternion["y"]
                z = quaternion["z"]
                w = quaternion["w"]

                await send_sensor_data_quaternion(websocket, x, y, z, w)
                # time.sleep(.05)
                # await asyncio.sleep(.5)

    return


async def main():
    print("WS server running on IP = {0}, Port = {1}".format(ip_address, port))
    async with websockets.serve(handle_connection, host=ip_address, port=port):
        await asyncio.Future()


asyncio.run(main())
