#!/usr/bin/env python3
"""
demo_vision.py — Quick ArUco detection demo.
Opens camera, draws markers on frame, prints distance + bearing.
Run on board: python3 demo_vision.py
"""

import cv2
import numpy as np
import math
import time

ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
ARUCO_PARAMS = cv2.aruco.DetectorParameters()
DETECTOR = cv2.aruco.ArucoDetector(ARUCO_DICT, ARUCO_PARAMS)

MARKER_SIZE_MM = 100.0
FOCAL_PX = 900.0  # tune per camera: python3 marker_vision.py calibrate

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("No camera found.")
    exit(1)

print("Detecting markers... press q to quit")
time.sleep(1)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = DETECTOR.detectMarkers(gray)

    if ids is not None:
        cv2.aruco.drawDetectedMarkers(frame, corners, ids)
        for i, marker_id in enumerate(ids.flatten()):
            pts = corners[i][0]
            cx = pts[:, 0].mean()
            cy = pts[:, 1].mean()
            side_px = (np.linalg.norm(pts[0] - pts[1]) + np.linalg.norm(pts[2] - pts[3])) / 2
            dist_mm = MARKER_SIZE_MM * FOCAL_PX / side_px
            bearing = math.degrees(math.atan2(cx - w / 2, FOCAL_PX))

            label = f"ID:{marker_id} {dist_mm/1000:.1f}m {bearing:+.0f}deg"
            cv2.putText(frame, label, (int(cx) - 60, int(cy) - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            print(f"  marker {marker_id}: {dist_mm/1000:.2f}m, bearing {bearing:+.1f} deg")
    else:
        print("  no markers", end="\r")

    cv2.imshow("ArUco Demo", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
