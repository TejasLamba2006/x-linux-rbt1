# rotation_test.py -- rotate robot, monitor yaw, stop at target
import urllib.request, json, time, asyncio, websockets

def get_yaw():
    r = urllib.request.urlopen('http://localhost:5000/state')
    return json.loads(r.read())['yaw']

async def main():
    print("=== Baseline yaw ===")
    baseline = get_yaw()
    print(f"  yaw = {baseline:.2f}")
    time.sleep(1)
    baseline = get_yaw()
    print(f"  yaw = {baseline:.2f}")

    target = 90  # rotate right 90 degrees
    tolerance = 5  # stop within ±5 degrees of target
    speed = 40

    async with websockets.connect("ws://localhost:8000/ws") as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print(f"  Connected: {msg[:80]}")

        # Set mode to controller
        await ws.send(json.dumps({"mode": "controller"}))
        await asyncio.sleep(0.5)

        # Start rotating right
        print(f"\n=== Rotating right (speed={speed}), target yaw={baseline + target:.1f} ===")
        await ws.send(json.dumps({"dir_rot": speed}))

        yaw_history = []
        start = time.time()
        while time.time() - start < 15:  # max 15 seconds
            await asyncio.sleep(0.2)
            yaw = get_yaw()
            elapsed = time.time() - start
            yaw_history.append((elapsed, yaw))
            print(f"  t={elapsed:.1f}s  yaw={yaw:.2f}  delta={yaw - baseline:.1f}")

            # Stop when we reach target ± tolerance
            if yaw >= (baseline + target - tolerance):
                break

        # Stop motors
        await ws.send(json.dumps({"dir_rot": 0}))
        await ws.send(json.dumps({"throttle": 0}))
        print(f"\n=== Stopped motors ===")

        # Let it settle
        print("=== Settling ===")
        for i in range(10):
            await asyncio.sleep(0.5)
            yaw = get_yaw()
            print(f"  t={i*0.5:.1f}s  yaw={yaw:.2f}")

        final = get_yaw()
        error = final - baseline - target
        print(f"\n=== RESULT: start={baseline:.2f} final={final:.2f} expected={baseline+target:.1f} error={error:.2f} ===")

asyncio.run(main())
