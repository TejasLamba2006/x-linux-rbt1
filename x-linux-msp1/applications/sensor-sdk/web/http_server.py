#!/usr/bin/python3

##
##############################################################################
# @file   http_server.py
# @author SRA-SAIL, Noida
# @brief  Module for HTTP server functionality
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


import asyncio
import socket
from aiohttp import web
import websockets
import mimetypes

import sensor_config as config
import utils


host = utils.get_ipaddress()
port = 80
ws_port = config.WS_PORT


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async for msg in ws:
        if msg.type == web.WSMsgType.text:
            await ws.send_str(f"Echo: {msg.data}")
        elif msg.type == web.WSMsgType.error:
            print(f"WebSocket connection closed with exception: {ws.exception()}")

    print("WebSocket connection closed")
    return ws


async def serve_page(request):
    with open("templates/index.html", "r") as f:
        content = f.read()
        content = content.replace("{{ws_address}}", str(host))
        content = content.replace("{{ws_port}}", str(ws_port))
    return web.Response(content_type="text/html", text=content)


async def serve_static(request):
    path = request.match_info["path"]
    content_type, _ = mimetypes.guess_type(path)
    try:
        with open("static/" + path, "rb") as f:
            content = f.read()
    except FileNotFoundError:
        raise web.HTTPNotFound()

    return web.Response(content_type=content_type, body=content)


app = web.Application()
app.router.add_get("/", serve_page)
app.router.add_get("/ws", websocket_handler)
app.router.add_get("/{path:.*\\.(html|css|js|png|jpg|jpeg|gif|ico|svg)}", serve_static)

web.run_app(app, host=host, port=port)
