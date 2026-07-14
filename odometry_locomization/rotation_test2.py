# rotation_test2.py -- rotate for fixed duration, measure result
import urllib.request, json, time, asyncio, websockets

def get_yaw():
    r = urllib.request.urlopen('http://localhost:5000/state')
    return json.loads(r.read())['yaw']

async def main():
    baseline = get_yaw()
    print(f"Baseline yaw = {baseline:.2f}")

    async with websockets.connect("ws://localhost:8000/ws") as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print(f"Connected: {msg[:60]}")

        await ws.send(json.dumps({"mode": "controller"}))
        await asyncio.sleep(0.5)

        # Rotate right for 3 seconds
        print("\n--- Rotating RIGHT for 3 seconds ---")
        await ws.send(json.dumps({"dir_rot": 40}))
        
        for i in range(15):
            await asyncio.sleep(0.2)
            yaw = get_yaw()
            delta = yaw - baseline
            print(f"  t={i*0.2:.1f}s  yaw={yaw:.2f}  delta={delta:.2f}")

        # Stop
        await ws.send(json.dumps({"dir_rot": 0}))
        await ws.send(json.dumps({"throttle": 0}))
        print("\n--- Motors stopped, settling ---")

        for i in range(10):
            await asyncio.sleep(0.5)
            yaw = get_yaw()
            print(f"  t={i*0.5:.1f}s  yaw={yaw:.2f}  delta={yaw-baseline:.2f}")

        final = get_yaw()
        total_rot = final - baseline
        print(f"\n=== RESULT: start={baseline:.2f} final={final:.2f} rotation={total_rot:.2f} ===")

        # Now rotate LEFT for 3 seconds to return
        print("\n--- Rotating LEFT for 3 seconds ---")
        await ws.send(json.dumps({"dir_rot": -40}))
        
        for i in range(15):
            await asyncio.sleep(0.2)
            yaw = get_yaw()
            print(f"  t={i*0.2:.1f}s  yaw={yaw:.2f}  delta={yaw-baseline:.2f}")

        await ws.send(json.dumps({"dir_rot": 0}))
        await ws.send(json.dumps({"throttle": 0}))
        print("\n--- Motors stopped, settling ---")

        for i in range(10):
            await asyncio.sleep(0.5)
            yaw = get_yaw()
            print(f"  t={i*0.5:.1f}s  yaw={yaw:.2f}  delta={yaw-baseline:.2f}")

        final = get_yaw()
        total_rot = final - baseline
        print(f"\n=== RESULT: start={baseline:.2f} final={final:.2f} rotation={total_rot:.2f} ===")

asyncio.run(main())
