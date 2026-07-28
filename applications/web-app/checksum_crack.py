#!/usr/bin/env python3
"""Brute-force the 2-byte checksum algorithm from the example frames in TASK.md.

Frame format: AA 55 <board_id> <cmd> <len> [payload...] <cksum_lo> <cksum_hi>
We test CRC-16 variants over several byte ranges and both endiannesses.
"""

# (name, full_frame_bytes)
FRAMES = [
    ("NOP",              bytes.fromhex("AA550A0000 51C2".replace(" ", ""))),
    ("SPEED_FWD",        bytes.fromhex("AA550A0103800000 3CDD".replace(" ", ""))),
    ("SPEED_REV",        bytes.fromhex("AA550A0203800000 78DD".replace(" ", ""))),
    ("TORQUE_FWD",       bytes.fromhex("AA550A0303800000 451D".replace(" ", ""))),
    ("TORQUE_REV",       bytes.fromhex("AA550A0403800000 F0DD".replace(" ", ""))),
    ("SET_MODE_SPEED",   bytes.fromhex("AA550A0500 5292".replace(" ", ""))),
    ("SET_MODE_TORQUE",  bytes.fromhex("AA550A0600 5262".replace(" ", ""))),
    ("START_MOTOR",      bytes.fromhex("AA550A0700 53F2".replace(" ", ""))),
    ("GET_STATUS",       bytes.fromhex("AA550A0800 5602".replace(" ", ""))),
    ("GET_SPEED",        bytes.fromhex("AA550A0900 5792".replace(" ", ""))),
    ("GET_TORQUE",       bytes.fromhex("AA550A0A00 5762".replace(" ", ""))),
    ("CLEAR_FAULTS",     bytes.fromhex("AA550A0B00 56F2".replace(" ", ""))),
    ("SET_ACCEL_ONLY",   bytes.fromhex("AA550A0C03000050 10C8".replace(" ", ""))),
    ("SET_TIME_ONLY",    bytes.fromhex("AA550A0D020020 1EB5".replace(" ", ""))),
    ("HEARTBEAT",        bytes.fromhex("AA550A0E00 55A2".replace(" ", ""))),
    ("SET_CURRENT_LIMIT",bytes.fromhex("AA550A0F028813 3918".replace(" ", ""))),
]

# sanity: split each frame into data + 2-byte checksum
def split(frame):
    return frame[:-2], frame[-2], frame[-1]

# ---- CRC-16 engine ----
def crc16(data, poly, init, refin, refout, xorout):
    crc = init
    for byte in data:
        if refin:
            byte = int(f"{byte:08b}"[::-1], 2)
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    if refout:
        crc = int(f"{crc:016b}"[::-1], 2)
    return crc ^ xorout

# byte ranges to try: which slice of the frame feeds the checksum
# frame = AA 55 id cmd len payload... ck1 ck2
# index:   0  1  2  3   4   5..
def ranges(frame):
    n = len(frame)
    return {
        "all_but_last2 (0..-2)":      frame[0:n-2],
        "id..payload (2..-2)":        frame[2:n-2],
        "cmd..payload (3..-2)":       frame[3:n-2],
        "len..payload (4..-2)":       frame[4:n-2],
        "payload_only (5..-2)":       frame[5:n-2],
        "header..payload (0..-2)":    frame[0:n-2],
    }

# candidate CRC-16 parameter sets (poly, init, refin, refout, xorout)
CANDIDATES = {
    "CRC-16/CCITT-FALSE": (0x1021, 0xFFFF, False, False, 0x0000),
    "CRC-16/XMODEM":      (0x1021, 0x0000, False, False, 0x0000),
    "CRC-16/KERMIT":      (0x1021, 0x0000, True,  True,  0x0000),
    "CRC-16/MODBUS":      (0x8005, 0xFFFF, True,  True,  0x0000),
    "CRC-16/ARC":         (0x8005, 0x0000, True,  True,  0x0000),
    "CRC-16/USB":         (0x8005, 0xFFFF, True,  True,  0xFFFF),
    "CRC-16/MAXIM":       (0x8005, 0x0000, True,  True,  0xFFFF),
    "CRC-16/IBM-3740":    (0x1021, 0xFFFF, False, False, 0x0000),
    "CRC-16/AUG-CCITT":   (0x1021, 0x1D0F, False, False, 0x0000),
    "CRC-16/GENIBUS":     (0x1021, 0xFFFF, False, False, 0xFFFF),
    "CRC-16/CCITT (init0)":(0x1021,0x0000, False, False, 0x0000),
    "CRC-16/CCITT (rev)": (0x8408, 0xFFFF, True,  True,  0x0000),
    "CRC-16/CCITT (rev x)":(0x8408,0xFFFF, True,  True,  0xFFFF),
    "CRC-16/DNP":         (0x3D65, 0x0000, True,  True,  0xFFFF),
    "CRC-16/CCITT-FALSE initFF xorFF":(0x1021,0xFFFF,False,False,0xFFFF),
}

def match_all(crc_fn, rng_key):
    """Return True if crc_fn over range rng_key reproduces BOTH checksum bytes
    for every frame, in either endianness."""
    for name, frame in FRAMES:
        data = ranges(frame)[rng_key]
        c = crc_fn(data)
        lo, hi = frame[-2], frame[-1]
        # try little-endian (lo=low byte) and big-endian
        if not ((c & 0xFF) == lo and (c >> 8) == hi) and \
           not ((c & 0xFF) == hi and (c >> 8) == lo):
            return False
    return True

def endianness(crc_fn, rng_key):
    """Determine which endianness matches, return 'LE'/'BE'/None."""
    le = be = True
    for name, frame in FRAMES:
        data = ranges(frame)[rng_key]
        c = crc_fn(data)
        lo, hi = frame[-2], frame[-1]
        if not ((c & 0xFF) == lo and (c >> 8) == hi):
            le = False
        if not ((c & 0xFF) == hi and (c >> 8) == lo):
            be = False
    if le: return "LE (ck1=low, ck2=high)"
    if be: return "BE (ck1=high, ck2=low)"
    return None

found = []
for cname, (poly, init, refin, refout, xorout) in CANDIDATES.items():
    fn = lambda d, p=poly, i=init, ri=refin, ro=refout, x=xorout: crc16(d, p, i, ri, ro, x)
    for rng_key in ranges(FRAMES[0][1]):
        if match_all(fn, rng_key):
            end = endianness(fn, rng_key)
            found.append((cname, rng_key, end))
            print(f"MATCH: {cname:40s} range={rng_key:28s} endian={end}")

if not found:
    print("No standard CRC-16 matched. Dumping per-frame CRC values for manual inspection...")
    print("\n--- CRC-16/CCITT-FALSE over id..payload (2..-2) ---")
    for name, frame in FRAMES:
        data = ranges(frame)["id..payload (2..-2)"]
        c = crc16(data, 0x1021, 0xFFFF, False, False, 0x0000)
        print(f"{name:20s} want={frame[-2]:02X}{frame[-1]:02X}  got={c:04X}  (LE:{c&0xFF:02X}{c>>8:02X})")
    print("\n--- CRC-16/MODBUS over id..payload (2..-2) ---")
    for name, frame in FRAMES:
        data = ranges(frame)["id..payload (2..-2)"]
        c = crc16(data, 0x8005, 0xFFFF, True, True, 0x0000)
        print(f"{name:20s} want={frame[-2]:02X}{frame[-1]:02X}  got={c:04X}  (LE:{c&0xFF:02X}{c>>8:02X})")
else:
    print(f"\n*** {len(found)} matching algorithm(s) found ***")
