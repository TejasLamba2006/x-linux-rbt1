# Application requirements

This is a web application including both front-end and backend that is used to control a robot

## Frontend Description
The frontend implements a FPV drone like interface. The interface needs to be mobile friendly, responsive, in landscape orientation.
The interface that has 2 joysticks (similar to the attached image) one on the Left and one on the right side, in between the joyticks there is a mode selection slider. The joysticks needs to be positioned such that they are accessible from users thumbs, e.g. when displaying on a larger screen, the joystick should be positioned on the lower side of the screen. Left side is used to control the throttle, and the right hand joystick is used of control the direction. 

### Left side joystick specs
Left side (Throttle) joystick consists of 4 concentric circles (with gradient), 
- outer most circle (c4) has a dotted border and solid color (a shade lighter than the background)
- next circle (c3) has a solid border and circular gradient fill and encloses circle c2. There are 2 arrowheads on the top and bottom side (in the area between c2 and c3)
- Next circle (c2) of grayish color and circular garadient encloses a smaller circle (c1) of whitish color (circular gradient), c1 is only slightly smaller than c2, c1 and c2 togather represent head / thumb of the joystick.
- The thumb of the joystick could be moved (touch and drag) only in up and down direction, on releasing it returns to the centre position. 
- The thumb position is sampled every 200ms and a command (json) is sent with values as follows 
```json
{"throttle": "val_throttle"}
```
where val_throttle is -100 to 100 based on thumb position


### Right side joystick specs
Same as left side joystick with following modifications
- c4 is enclosed by a circle c5 which can be rotated and represents a dial like interface
- the area between c4 and c5 contains eually spaced ticks, is touch sensitive and can be rotated using a touch and drag guesture. it also contains the small circle which represents the current postion of the dial. 
- There are 4 arrowheads on top, bottom, right and left side (in the area between c2 and c3)
- The thumb of the joystick could be moved (touch and drag) in any direction, on releasing it returns to the centre position. 
- The thumb position is sampled every 200ms and a command (json) is sent with values as follows 
```json
{"dir_x": "val_x", 
"dir_y": "val_y"}
```
where val_x and val_y are -100 to 100 based on thumb position

- The outermost dial is sampled every 200ms and a command (json) is sent with values as follows 
```json
{"dir_rot": "val_rot"}
```
where val_rot are 0 to 360 based on dial position

### Mode Selector Specs
Mode selector slider is situated, between the left and right joystick (aligned lower part of the UI).
It has following options
- Locked
- Controller
- Follow-me
- Autopilot

When the mode is changed, the command would be sent as 
{"mode": "val_mode"}
val_mode = locked/controller/follow-me/autopilot

## Backend Decsription

Backend is implemented using fast API and websockets, the web pages and static resources are also served from the same backend.

When json commands are received from the fornt-end specific async functions are called to effect the robot movement


## Robot Movement Middleware

### Lower level motor APIs expected by this middleware are of the form

```python
rover_move_ll(pwm_front_left, pwm_front_right, pwm_rear_right, pwm_rear_left)
```

where pwm values are in percent (-100 to 100)

### High Level API exposed the middleware are as follows

```python
rover_move(throttle, dir_rot)
```
Moves the rover while rotating if dir_rot (-100 to 100) is provided. dir_rot == 100 means maximum rotation radius possible

```python
rover_mechanum_move(throttle, dir_x, dir_y)
```
This API moves the rover laterally (Mechanum control), throttle in percertage (-100 to 100), dir_x / dir_y are x and y components of the joystick direction input by user (-100 to 100)

```python
rover_rorate(dir_rot)
```
rotates the rover to specific angle (uses IMU), dir_rot (0-360)
