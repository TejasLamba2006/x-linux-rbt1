# LinkedIn Post — Vision Marker Detection

---

Added ArUco marker detection to a robot running on an STM32MP board. You print a marker, stick it on a wall or table, point a camera at it, and the robot drives itself to that spot. No joystick, no remote, no pre-mapped path.

The detection pipeline is simple: OpenCV finds the ArUco marker in each frame, computes real-world distance from the marker's pixel size using a pinhole camera model, and gets heading from its position in the frame. One focal length measurement is all you need to calibrate. I also cross-check distance against a VL53L5CX ToF sensor so the robot doesn't overshoot.

This works on Arduino too. ArUco detection with OpenCV is lightweight enough for a Raspberry Pi or any board running Python. The core loop is: capture frame, detect marker, compute distance + bearing, send motor commands. You can wire that into whatever drive system you have.

Camera matters a lot for range. The STM32 board camera I'm using is mediocre. Detection works out to about 5 meters in good lighting. Swap in an iPhone camera or a decent USB webcam and you're looking at 15-20 meters easily. The math doesn't change, you just get more pixels on the marker at distance.

Where this gets interesting for humanoid robots: vision-based navigation without GPS or pre-built maps. A humanoid with a chest-mounted camera can walk toward a marker, follow a person carrying one, or chain multiple markers into a walking path. The same detect-and-drive loop works whether you're driving wheels or planning footstep sequences.

I built three modes into the system:
- Navigate to a single marker and stop at a set distance
- Follow-me mode that tracks a marker as you walk around with it
- Waypoint autopilot that chains multiple markers into a path

Still tuning focal length calibration and motor stall speeds per board, but it works. Recording a demo video next.

#Robotics #ComputerVision #Arduino #STM32 #ArUco #OpenCV #HumanoidRobotics #EmbeddedSystems
