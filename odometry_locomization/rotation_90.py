# rotation_90.py -- precise 90-degree rotation test
import urllib.request, json, time, asyncio, websockets

def get_yaw():
    r = urllib.request.urlopen('http://localhost:5000/state')
    return json.loads(r.read())['yaw']

def zero_yaw():
    req = urllib.request.Request("http://localhost:5000/zero_yaw", data=b"", method="POST")
    urllib.request.urlopen(req)

async def main():
    print("=== PHASE 1: Zero heading ===")
    zero_yaw()
    await asyncio.sleep(2)
    baseline = get_yaw()
    print(f"  Baseline after zero: {baseline:.2f}")

    async with websockets.connect("ws://localhost:8000/ws") as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        await ws.send(json.dumps({"mode": "controller"}))
        await asyncio.sleep(0.5)

        # First: measure rotation rate at speed 30
        print("\n=== PHASE 2: Measure rotation rate (3s at speed 30) ===")
        t0 = time.time()
        await ws.send(json.dumps({"dir_rot": 30}))

        samples = []
        while time.time() - t0 < 4.0:
            await asyncio.sleep(0.1)
            yaw = get_yaw()
            t = time.time() - t0
            samples.append((t, yaw))
            if t < 3.0 or t > 3.1:
                print(f"  t={t:.2f}s  yaw={yaw:.2f}")

        await ws.send(json.dumps({"dir_rot": 0}))
        await asyncio.sleep(1)
        after_stop = get_yaw()
        print(f"  After stop + settle: {after_stop:.2f}")

        # Compute rate from 0.5s to 2.5s (steady state, exclude acceleration/decel)
        steady = [(t, y) for t, y in samples if 0.5 <= t <= 2.5]
        if len(steady) >= 2:
            dt = steady[-1][0] - steady[0][0]
            dy = steady[-1][1] - steady[0][1]
            rate = dy / dt
            print(f"  Steady-state rate: {rate:.2f} deg/s (from {steady[0][1]:.1f} to {steady[-1][1]:.1f} over {dt:.2f}s)")

        # Now do a true 90-degree rotation
        print("\n=== PHASE 3: Rotate 90 degrees ===")
        zero_yaw()
        await asyncio.sleep(2)
        start = get_yaw()
        print(f"  Start: {start:.2f}")

        # Calculate time needed for 90 degrees at measured rate
        if abs(rate) > 1:
            time_for_90 = 90.0 / abs(rate)
            print(f"  Estimated time for 90deg: {time_for_90:.2f}s")
        else:
            time_for_90 = 3.0
            print(f"  Using default time: {time_for_90:.2f}s")

        # Rotate
        await ws.send(json.dumps({"dir_rot": 30}))
        await asyncio.sleep(time_for_90)
        await ws.send(json.dumps({"dir_rot": 0}))
        await asyncio.sleep(2)

        final = get_yaw()
        error = final - 90.0
        print(f"  Final yaw: {final:.2f}")
        print(f"  Error from 90deg: {error:.2f} degrees")

        # Also test negative direction
        print("\n=== PHASE 4: Rotate -90 degrees (left) ===")
        zero_yaw()
        await asyncio.sleep(2)
        start2 = get_yaw()
        print(f"  Start: {start2:.2f}")

        await ws.send(json.dumps({"dir_rot": -30}))
        await asyncio.sleep(time_for_90)
        await ws.send(json.dumps({"dir_rot": 0}))
        await asyncio.sleep(2)

        final2 = get_yaw()
        error2 = final2 - (-90.0)
        print(f"  Final yaw: {final2:.2f}")
        print(f"  Error from -90deg: {error2:.2f} degrees")

        print(f"\n=== SUMMARY ===")
        print(f"  Right 90deg test: final={final:.2f}, error={error:.2f}")
        print(f"  Left 90deg test:  final={final2:.2f}, error={error2:.2f}")

asyncio.run(main())
