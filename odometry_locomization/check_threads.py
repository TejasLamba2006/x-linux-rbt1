import os, glob
pid = 7332
tasks = glob.glob(f"/proc/{pid}/task/*")
print(f"Thread count: {len(tasks)}")
for t in tasks:
    tid = os.path.basename(t)
    try:
        with open(f"{t}/comm") as f:
            name = f.read().strip()
        with open(f"{t}/status") as f:
            lines = f.readlines()
        state = [l for l in lines if l.startswith("State:")]
        print(f"  TID {tid}: comm={name} {state[0].strip() if state else ''}")
    except:
        print(f"  TID {tid}: (error reading)")
