# check_yaw.py -- poll /state endpoint and print yaw over time
import urllib.request, json, time
for i in range(10):
    r = urllib.request.urlopen('http://localhost:5000/state')
    d = json.loads(r.read())
    print(f'yaw={d["yaw"]:.2f} x={d["x"]:.1f} y={d["y"]:.1f}')
    time.sleep(1)
