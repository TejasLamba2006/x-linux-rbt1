# stop_box.py -- stop MKBOXPRO streaming
import asyncio, sys
sys.path.insert(0, '/usr/tejas/x-linux-rbt1/odometry_locomization')
from imu_usb_mkbox import MkBoxUsbGyro

async def main():
    g = MkBoxUsbGyro()
    print("stopping MKBOXPRO streaming...")
    await g.stop()
    print("done")

asyncio.run(main())
