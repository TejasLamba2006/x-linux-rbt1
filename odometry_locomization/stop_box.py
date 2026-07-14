# stop_box.py -- stop MKBOXPRO streaming
import asyncio
from imu_usb_mkbox import MkBoxUsbGyro

async def main():
    g = MkBoxUsbGyro()
    print("stopping MKBOXPRO streaming...")
    await g.stop()
    print("done")

asyncio.run(main())
