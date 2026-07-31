#!/usr/bin/env python3
# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# BSD 3-Clause License. See uart_motors.py header.
"""
Motor Debugger Server -- a standalone web console for driving individual wheels.

Run on the board (independent of main.py):

    python3 motor_debug_server.py            # serves http://<board-ip>:8080
    python3 motor_debug_server.py --port 9000

Opens the browser to an industrial-styled control panel where you can:
  * pick any wheel (FL/FR/RL/RR) and drive it forward/reverse at a chosen speed
  * init / clear-faults / read status per wheel
  * hit a big STOP ALL
  * watch a live TX/RX frame log (which bytes went to which wheel)

It reuses uart_motors for the actual protocol, so the frames it sends are
identical to what the real controller sends.
"""

import argparse
import json
import logging
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import uart_motors as um

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("motor_debug")

# ---------------------------------------------------------------------------
# Frame log (ring buffer) -- captures every TX/RX so the UI can show it.
# ---------------------------------------------------------------------------
LOG_MAX = 200
_frame_log = deque(maxlen=LOG_MAX)
_log_lock = threading.Lock()
_log_seq = 0


def record(direction, wheel, label, frame_hex, resp_hex=""):
    global _log_seq
    with _log_lock:
        _log_seq += 1
        _frame_log.append({
            "seq": _log_seq,
            "t": time.strftime("%H:%M:%S"),
            "dir": direction,      # "TX" or "RX"
            "wheel": wheel,
            "label": label,
            "frame": frame_hex,
            "resp": resp_hex,
        })


def snapshot_log(after_seq=0):
    with _log_lock:
        items = [e for e in _frame_log if e["seq"] > after_seq]
        return items, _log_seq


# ---------------------------------------------------------------------------
# Motor controller wrapper -- logs every frame it sends/receives.
# ---------------------------------------------------------------------------
class DebugMotors:
    def __init__(self):
        self.ctrl = um.UARTMotors()
        self.status = {}   # wheel -> "closed" | "open" | "ready"

    def connect(self):
        result = self.ctrl.connect()
        for wheel, ok in result.items():
            self.status[wheel] = "open" if ok else "closed"
        return result

    def _board(self, wheel):
        return self.ctrl.boards.get(wheel)

    def _send(self, wheel, cmd, payload=b"", label=""):
        board = self._board(wheel)
        if board is None or board.ser is None:
            record("TX", wheel, label or um.CMD_NAMES.get(cmd, "?"), "(not connected)")
            return b""
        frame = um.build_frame(cmd, payload, board.board_id)
        record("TX", wheel, label or um.CMD_NAMES.get(cmd, "?"), frame.hex(" ").upper())
        board.send_frame(frame)
        resp = board.read_response(timeout=0.2)
        if resp:
            record("RX", wheel, "response", resp.hex(" ").upper())
        return resp

    def init_wheel(self, wheel):
        self._send(wheel, um.CMD_CLEAR_FAULTS, label="CLEAR_FAULTS")
        self._send(wheel, um.CMD_SET_MODE_SPEED, label="SET_MODE_SPEED")
        self._send(wheel, um.CMD_START_MOTOR, label="START_MOTOR")
        self.status[wheel] = "ready"
        self.ctrl._ready.add(wheel)

    def drive(self, wheel, speed, direction):
        """speed 0-100, direction 0=fwd 1=rev. Mirrors UARTMotors.set_speed."""
        if self.status.get(wheel) != "ready":
            self.init_wheel(wheel)
        magnitude = int(max(0, min(100, speed)) * 255 / 100)
        if magnitude == 0:
            self._send(wheel, um.CMD_SPEED_FWD, um.speed_payload(0), label="STOP(0)")
            return
        # Same wiring swap as the real controller: forward -> SPEED_REV opcode.
        cmd = um.CMD_SPEED_FWD if direction else um.CMD_SPEED_REV
        name = "SPEED_FWD" if cmd == um.CMD_SPEED_FWD else "SPEED_REV"
        self._send(wheel, cmd, um.speed_payload(magnitude),
                   label=f"{name}({magnitude})")

    def stop_wheel(self, wheel):
        self._send(wheel, um.CMD_SPEED_FWD, um.speed_payload(0), label="STOP")

    def stop_all(self):
        for wheel in self.ctrl.boards:
            self.stop_wheel(wheel)

    def clear_faults(self, wheel):
        self._send(wheel, um.CMD_CLEAR_FAULTS, label="CLEAR_FAULTS")

    def get_status(self, wheel):
        resp = self._send(wheel, um.CMD_GET_STATUS, label="GET_STATUS")
        return resp.hex(" ").upper() if resp else "(no response)"


MOTORS = DebugMotors()

# ---------------------------------------------------------------------------
# HTML console
# ---------------------------------------------------------------------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Motor Debugger</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --panel2: #1c2330; --line: #2d3748;
    --txt: #e6edf3; --dim: #8b949e; --accent: #ff8c00; --accent2: #ffa94d;
    --green: #2ea043; --red: #f85149; --blue: #58a6ff; --yellow: #d29922;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--txt);
    font-family: "Segoe UI", system-ui, sans-serif; font-size: 14px;
  }
  header {
    background: linear-gradient(90deg, #1a1f2b, #0d1117);
    border-bottom: 2px solid var(--accent);
    padding: 14px 20px; display: flex; align-items: center; gap: 16px;
  }
  header h1 { margin: 0; font-size: 20px; letter-spacing: 1px; }
  header .tag { color: var(--accent); font-weight: 700; }
  header .sub { color: var(--dim); font-size: 12px; }
  .stopall {
    margin-left: auto; background: var(--red); color: #fff; border: none;
    padding: 12px 26px; font-size: 16px; font-weight: 800; border-radius: 6px;
    cursor: pointer; letter-spacing: 1px; box-shadow: 0 0 12px rgba(248,81,73,.5);
  }
  .stopall:active { transform: scale(.97); }
  .layout { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px; }
  @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
  .wheels { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .card {
    background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
    padding: 14px; position: relative;
  }
  .card h2 {
    margin: 0 0 4px; font-size: 15px; display: flex; align-items: center; gap: 8px;
  }
  .card .pos { color: var(--dim); font-size: 11px; margin-bottom: 10px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--dim); }
  .dot.open { background: var(--yellow); }
  .dot.ready { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .dot.closed { background: var(--red); }
  .speedrow { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
  .speedrow input[type=range] { flex: 1; accent-color: var(--accent); }
  .speedrow .val { width: 46px; text-align: right; color: var(--accent2); font-weight: 700; }
  .btns { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 6px; }
  button.ctrl {
    border: 1px solid var(--line); background: var(--panel2); color: var(--txt);
    padding: 9px 6px; border-radius: 5px; cursor: pointer; font-size: 13px; font-weight: 600;
  }
  button.ctrl:hover { border-color: var(--accent); color: var(--accent2); }
  button.ctrl:active { transform: scale(.97); }
  button.fwd { border-color: var(--green); }
  button.rev { border-color: var(--blue); }
  button.stop { border-color: var(--red); grid-column: span 2; }
  .mini { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-top: 6px; }
  .mini button { font-size: 11px; padding: 6px 2px; }
  .status { margin-top: 8px; font-size: 11px; color: var(--dim); font-family: monospace;
            background: #0a0e14; padding: 5px 7px; border-radius: 4px; min-height: 16px;
            word-break: break-all; }
  .logpanel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
              padding: 14px; display: flex; flex-direction: column; height: 100%; }
  .logpanel h2 { margin: 0 0 10px; font-size: 15px; }
  .logpanel .bar { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
  .logpanel .bar label { font-size: 12px; color: var(--dim); }
  #log {
    flex: 1; overflow-y: auto; background: #0a0e14; border-radius: 5px; padding: 8px;
    font-family: "Cascadia Code", Consolas, monospace; font-size: 12px; line-height: 1.5;
    max-height: 70vh;
  }
  .entry { padding: 2px 0; border-bottom: 1px solid #161b22; }
  .entry .t { color: var(--dim); }
  .entry .wh { color: var(--accent2); font-weight: 700; }
  .entry .tx { color: var(--green); }
  .entry .rx { color: var(--blue); }
  .entry .lb { color: var(--txt); }
  .entry .fr { color: var(--dim); word-break: break-all; }
</style>
</head>
<body>
<header>
  <h1><span class="tag">&#9881;</span> MOTOR DEBUGGER</h1>
  <span class="sub">STM32MP257 rover &middot; 4&times; Nucleo + STEVAL-IHM023V3 &middot; UART 115200</span>
  <button class="stopall" onclick="stopAll()">&#9632; STOP ALL</button>
</header>

<div class="layout">
  <div class="wheels" id="wheels"></div>

  <div class="logpanel">
    <h2>Frame Log (TX / RX)</h2>
    <div class="bar">
      <label><input type="checkbox" id="autoscroll" checked> autoscroll</label>
      <button class="ctrl" style="padding:4px 10px" onclick="clearLog()">clear</button>
      <span style="margin-left:auto;color:var(--dim);font-size:11px" id="logcount"></span>
    </div>
    <div id="log"></div>
  </div>
</div>

<script>
const WHEELS = [
  {id:"FL", name:"Front Left",  port:"/dev/ttyACM1"},
  {id:"FR", name:"Front Right", port:"/dev/ttyACM3"},
  {id:"RL", name:"Rear Left",   port:"/dev/ttyACM0"},
  {id:"RR", name:"Rear Right",  port:"/dev/ttyACM2"},
];

function el(id){ return document.getElementById(id); }

function buildCards(){
  const wrap = el("wheels");
  WHEELS.forEach(w => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <h2><span class="dot" id="dot-${w.id}"></span>${w.id} &mdash; ${w.name}</h2>
      <div class="pos">${w.port}</div>
      <div class="speedrow">
        <input type="range" min="0" max="100" value="50" id="spd-${w.id}"
               oninput="el('spdv-${w.id}').textContent=this.value">
        <span class="val" id="spdv-${w.id}">50</span>
      </div>
      <div class="btns">
        <button class="ctrl fwd" onclick="drive('${w.id}',0)">&#9650; FORWARD</button>
        <button class="ctrl rev" onclick="drive('${w.id}',1)">&#9660; REVERSE</button>
        <button class="ctrl stop" onclick="stopWheel('${w.id}')">&#9632; STOP</button>
      </div>
      <div class="mini">
        <button class="ctrl" onclick="initWheel('${w.id}')">INIT</button>
        <button class="ctrl" onclick="clearFaults('${w.id}')">CLR FLT</button>
        <button class="ctrl" onclick="getStatus('${w.id}')">STATUS</button>
      </div>
      <div class="status" id="st-${w.id}">idle</div>
    `;
    wrap.appendChild(card);
  });
}

function setSt(w, msg){ el("st-"+w).textContent = msg; }

async function api(path, body){
  const r = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: {"Content-Type":"application/json"},
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json();
}

async function drive(w, dir){
  const speed = parseInt(el("spd-"+w).value, 10);
  setSt(w, (dir?"REVERSE":"FORWARD")+" @ "+speed);
  await api("/api/drive", {wheel:w, speed:speed, direction:dir});
}
async function stopWheel(w){ setSt(w,"STOPPED"); await api("/api/stop", {wheel:w}); }
async function stopAll(){
  WHEELS.forEach(w=>setSt(w,"STOPPED"));
  await api("/api/stop_all", {});
}
async function initWheel(w){ setSt(w,"initializing..."); await api("/api/init", {wheel:w}); setSt(w,"ready"); }
async function clearFaults(w){ setSt(w,"clearing faults"); await api("/api/clear_faults", {wheel:w}); }
async function getStatus(w){
  setSt(w,"reading status...");
  const r = await api("/api/status", {wheel:w});
  setSt(w, "status: " + (r.status||"?"));
}

// ---- log polling ----
let lastSeq = 0;
function clearLog(){ el("log").innerHTML = ""; lastSeq = 0; }
async function pollLog(){
  try {
    const r = await fetch("/api/log?after="+lastSeq);
    const data = await r.json();
    const box = el("log");
    data.entries.forEach(e => {
      lastSeq = Math.max(lastSeq, e.seq);
      const d = document.createElement("div");
      d.className = "entry";
      const dirCls = e.dir === "TX" ? "tx" : "rx";
      d.innerHTML = `<span class="t">${e.t}</span> `
        + `<span class="${dirCls}">${e.dir}</span> `
        + `<span class="wh">[${e.wheel}]</span> `
        + `<span class="lb">${e.label}</span><br>`
        + `<span class="fr">&nbsp;&nbsp;${e.frame}</span>`;
      box.appendChild(d);
    });
    if (data.entries.length){
      el("logcount").textContent = "seq "+data.seq;
      if (el("autoscroll").checked) box.scrollTop = box.scrollHeight;
      // trim to last 300 entries in DOM
      while (box.children.length > 300) box.removeChild(box.firstChild);
    }
  } catch(e){}
}

// ---- status dots ----
async function pollStatus(){
  try {
    const r = await fetch("/api/status_all");
    const data = await r.json();
    WHEELS.forEach(w => {
      const dot = el("dot-"+w.id);
      const st = (data.status && data.status[w.id]) || "closed";
      dot.className = "dot " + st;
      dot.title = st;
    });
  } catch(e){}
}

buildCards();
setInterval(pollLog, 500);
setInterval(pollStatus, 2000);
pollStatus();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet default logging
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._html(INDEX_HTML)
        elif self.path.startswith("/api/log"):
            after = 0
            if "?" in self.path:
                q = self.path.split("?", 1)[1]
                for kv in q.split("&"):
                    if kv.startswith("after="):
                        try:
                            after = int(kv.split("=", 1)[1])
                        except ValueError:
                            after = 0
            entries, seq = snapshot_log(after)
            self._json({"entries": entries, "seq": seq})
        elif self.path.startswith("/api/status_all"):
            self._json({"status": MOTORS.status})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "bad json"}, 400)
            return

        wheel = data.get("wheel")
        path = self.path
        try:
            if path == "/api/drive":
                MOTORS.drive(wheel, int(data.get("speed", 0)), int(data.get("direction", 0)))
                self._json({"ok": True})
            elif path == "/api/stop":
                MOTORS.stop_wheel(wheel)
                self._json({"ok": True})
            elif path == "/api/stop_all":
                MOTORS.stop_all()
                self._json({"ok": True})
            elif path == "/api/init":
                MOTORS.init_wheel(wheel)
                self._json({"ok": True})
            elif path == "/api/clear_faults":
                MOTORS.clear_faults(wheel)
                self._json({"ok": True})
            elif path == "/api/status":
                self._json({"status": MOTORS.get_status(wheel)})
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            logger.exception("handler error")
            self._json({"error": str(e)}, 500)


def main():
    ap = argparse.ArgumentParser(description="Motor debugger web console")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    logger.info("Connecting to motor boards...")
    result = MOTORS.connect()
    for wheel, ok in result.items():
        logger.info("  %s: %s", wheel, "OPEN" if ok else "FAILED")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    logger.info("Motor debugger on http://%s:%d", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down, stopping motors...")
        MOTORS.stop_all()
        server.shutdown()


if __name__ == "__main__":
    main()
